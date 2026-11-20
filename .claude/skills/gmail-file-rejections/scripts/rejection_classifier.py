#!/usr/bin/env python3
"""Sentence-level job-rejection classifier (DE / EN / NL, a little SV/NO/PL/FR/ES).

A single keyword such as "leider" / "unfortunately" proves nothing ("leider verzögert sich der
Auswahlprozess", "unfortunately we need to reschedule", "unfortunately we can't reply to every
candidate"). A message counts as a rejection only if ONE SENTENCE of the sender's own text states
the decision against the candidate, using a decision phrase mined from the user's ~2,500 filed
rejection emails, and that sentence is not hypothetical, a request to act, a delay notice, a
scheduling remark, or quoted/forwarded text.

    from rejection_classifier import classify
    r = classify(frm, subject, body)   # -> {"verdict", "sentence", "why"}

verdict   (PRECISION FIRST: a false positive hides a real email, a false negative only costs a manual look)
  REJECTION      a specific decision sentence in the sender's own (unquoted) text, near the top, and the
                 message contains no interview invitation / request for action anywhere
  UNCLEAR        anything doubtful: generic "leider … nicht" wording without a decision phrase, decision
                 wording only in quote/subject/conditional sentences, or an invitation/action request in the
                 same message -> a human reads it; NEVER file automatically
  NOT_REJECTION  otherwise (confirmations, invitations, delays, tests, newsletters, user-sent mail)

CLI (to evaluate or tune on downloaded mail; see evaluate_classifier.py for precision/recall):
    python rejection_classifier.py --emails emails.json --bodies bodies.json [--show REJECTION]
"""
import os
import argparse, collections, json, re

# --------------------------------------------------------------------------------------------
# Tier 1: decision phrases. Each one, inside a sentence, says "you are out / position gone".
# --------------------------------------------------------------------------------------------
DECISION = [
    # --- German -------------------------------------------------------------------------
    r"nicht\b.{0,50}\b(berücksichtig|beruecksichtig|einbezieh|einbezogen)\w*",      # nicht (weiter) (zu) berücksichtigen
    r"nicht (mit )?in (die|den) (engere|engste|engeren|engsten|nähere)\w* (auswahl|wahl|kreis)",
    r"nicht in den engsten kreis",
    r"in die (engere|engste) (wahl|auswahl) (gezogen|genommen)",                     # (others) in die engere Wahl genommen
    r"nicht (mehr )?(im|in dem|für das|für den) (weiteren |weiterem )?(auswahl|bewerbungs|bewerber|besetzungs)\w*",
    r"(aus dem|im) (weiteren )?(auswahl|bewerbungs)\w* (ausscheiden|ausgeschieden|ausgeschlossen)",
    r"(vorauswahl|auswahl) getroffen",
    r"keine? (zusage|einladung) (machen|geben|aussprechen|erteilen)\w*",
    r"\babsage\b|\babzusagen\b|\babsagen (zu )?müssen\b|sagen (wir|ihnen|dir|euch) ab\b|leider absagen",
    r"nicht (weiter )?(zu )?(verfolgen|fortführen|fortsetzen|führen|weiterführen|weiterzuführen|weiterzuverfolgen)\w*",
    r"gegen eine fortführung|nicht zu der erhofften zusammenarbeit",
    r"entschieden\b.{0,100}\b(andere|anderen|eine/n|mitbewerb|weitere)\S*.{0,60}(bewerb|kandidat|person|profil|mitbewerb)",
    r"(andere|anderen|eine/n|mitbewerb|weitere)\S*\s.{0,40}(bewerb|kandidat|person|profil|mitbewerb)\S*.{0,60}entschieden",
    r"für mitbewerbende|für (andere|anderen) (bewerber|kandidat)|nicht für (dich|sie|euch|ihre|deine) (entschieden|ent)\w*",
    r"(entschieden|haben wir uns|gezogen|genommen)\b.{0,160}(kandidat|bewerber)\S*.{0,100}(besser|näher|genauer|passt|passen|entsprech|noch besser|zugeschnitten)",
    r"(kandidat|bewerber)\S*.{0,100}\b(deren|die)\b.{0,80}(besser|genauer|näher|noch besser|noch mehr|mehr).{0,60}(passen|passt|entsprech|zugeschnitten|anforderung)",
    r"(besser|geeigneter\w*|passender\w*).{0,60}(kandidat|bewerber)\S*.{0,40}entschieden",
    r"(andere|anderen|weitere)\w*(\s+\w+){0,2}\s+(bewerber|kandidat|bewerbungen|profile)\S*.{0,100}(passen|entsprech|überzeug|besser|vorgezogen|vorzug|näher)",
    r"(stelle|position|vakanz|aufgabe)\w* .{0,60}(bereits |inzwischen |schon |leider |zwischenzeitlich )*(besetzt|vergeben)",
    r"anderweitig (zu )?(besetz|vergeben)\w*",
    r"(profil|bewerbung|qualifikation)\w* (passt|passen|entspricht|entsprechen) (leider |einfach |nicht ganz |derzeit |aktuell )*(nicht|nur teilweise)|passt (einfach )?nicht in unser",
    r"keine? (passende|geeignete|offene)\w* (position|stelle|vakanz|aufgabe|rolle)\w* (anbieten|vergeben|bieten|haben)",
    r"kein(e|en)? (persönliche[sn]? )?(gespräch|interview|vorstellungsgespräch)\w* (anbieten|führen|einladen|vereinbaren)|nicht zu einem (gespräch|interview) einzuladen",
    r"es hat (dieses mal |diesmal |leider )*nicht geklappt|hat es (dieses mal |diesmal )?(leider )?nicht geklappt|keine positive nachricht",
    r"(bewerbungsverfahren|auswahlverfahren|auswahlprozess|verfahren)\w* .{0,40}(abgeschlossen|beendet|abgebrochen|eingestellt)|(bewerbung|bewerbungsverfahren)\w* .{0,120}(beendet|abgelehnt)",
    r"(stelle|position)\w* .{0,40}(nicht (mehr )?(zu )?besetz|zurückgezogen|gestrichen)|schließen (wir )?das (auswahl|bewerbungs)\w* (für diese|ab)",
    r"(können|koennen) wir (aktuell|derzeit|momentan|zurzeit|zur zeit|leider|im moment)?\s*(nicht|keine?)\s*(weiter ?planen|weiter ?machen|weiter ?verfolgen)|nicht weiter ?planen",
    r"täglich treffen wir viele entscheidungen|leichtfallen.{0,60}(absage|leider)",
    r"(teilen|teile) wir (dir|ihnen|euch) (heute )?mit, dass.{0,80}(nicht|kein|andere|leider)",
    # --- after measuring recall on 500 filed rejections -------------------
    r"\bnicht\b.{0,60}\bfortfahren\b",                                                    # nicht mit deiner Bewerbung / im Bewerbungsprozess fortfahren
    r"nicht für (deine|ihre|eure?) bewerbung (\w+ )?entschieden|bewerbung (leider )?keinen erfolg|nicht in betracht ziehen|nicht weiterverfolgen",
    r"\b(position|stelle|arbeitsplatz)\b.{0,100}\bnicht anbieten (können|zu können)|\bkeine?n? (position|stelle|arbeitsplatz)\b.{0,60}\banbieten|keine position .{0,40}vakant",
    r"(nächsten|weiteren) schritt.{0,40}nicht (gehen|machen|nehmen)|zu dem ergebnis gekommen.{0,40}nicht|nicht weitergeht",
    r"(passen|passt) .{0,40}nicht (gut )?genug zusammen.{0,60}prozess.{0,30}(weiter|fort)\w*|den prozess (gemeinsam )?(nicht )?weiterzuführen|um den prozess .{0,30}weiterzuführen",
    r"keine positive (rückmeldung|nachricht|antwort)|müssen wir (den )?prozess .{0,25}(stoppen|beenden)|konnte(n)? .{0,40}nicht besetzt werden",
    # --- English ------------------------------------------------------------------------
    r"decided to not( to)? (move|proceed|continue|take|pursue|go|progress)\w*|decision not to (take|move|proceed|continue|progress|pursue)\w*|could not be filled",
    r"\b(not|n['’]t) (be )?(moving|move|proceed\w*|progress\w*|pursu\w*|continu\w*|taking|take)\b.{0,30}\b(forward|further|ahead|any further|your (application|candidacy)|to the next)",
    r"(aren|are|won|will|isn|is) ?(['’]?t| not)? (be )?(moving|going) forward with (your|the) (application|candidacy)|(aren|are) not moving forward",
    r"decided (not )?to (move|go|proceed|pursue|continue)\w* (forward )?with (other|another|different|a (different )?candidate|candidates|applications)",
    r"decided not to (move|proceed|continue|pursue|progress|take|invite|consider)\w*",
    r"(decided|chosen|concluded|will be moving|are moving|moving) (to )?(continue|proceed|move forward|forward|go ahead)\b.{0,100}(candidate|applicant|application|others|smaller number|fewer|better fit|closely)",
    r"(not|n['’]t) (been )?(selected|shortlisted|chosen|successful|considered)\b|no longer (being )?considered",
    r"\b(could ?n['’]?t|can['’]?t|cannot|can not|did ?n['’]?t|won['’]?t|would ?n['’]?t|will not|would not|could not|do not|don['’]t) (shortlist|select|consider|offer|invite|progress|proceed|move forward|continue)\w*",
    r"\bnot (continue|proceed|pursue|progress) (with )?(the |this |your )?(selection|recruitment|hiring|application|process|candidacy|with you)",
    r"(candidates|applicants)\w* (that|who|whose)\b.{0,60}(match|fit|align|suit)\w* (better|more|closely)|we have to make choices|open only to candidates",
    r"(unable|not able) to (move|proceed|progress|continue|consider|invite)\w* (you|your|further|forward|with)|(unable|not able|cannot|can['’]?t|won['’]?t be able to) (to )?offer you (an interview|a position|a role|the role|the position|this position|this role|this opportunity|a job|a place)|won['’]?t be able to (invite|move|consider|proceed)",
    r"^(?=.*\b(decided|chosen|choose|chose|proceed\w*|mov\w+ forward|continu\w*|select\w*|prefer\w*|favou?r\w*|went with|going with|pursu\w*|progress\w*|entschieden)\b).*\b(other|another|different|stronger|more (suitable|qualified|closely|experienced)) (candidate|applicant|profile)s?\b",
    r"(position|role|vacancy|job|post)\w* (has|have) (already |now |since )?(been )?(filled|closed|cancelled|put on hold|withdrawn)|(filled|closed) (the|this) (position|role|vacancy)|otherwise (occupied|filled)",
    r"(vacancy|position|role).{0,40}(has now been|is now|was) closed|closing the (selection|recruitment|hiring) process|(unfortunately|leider|regret|have to|must|need to|müssen).{0,40}(cancel|close) your application",
    r"^(?=.*\b(application|candidacy|position|role|vacancy|not|unable|other|filled|selected|proceed\w*|forward|unsuccessful|decided)\b).*(regret to (inform|tell|advise)|we regret that)",
    r"not (a )?(strong |good |close |perfect |quite )?(match|fit)\b|no (strong|good|suitable|matching) (match|fit|role|position)|don['’]t see a (strong )?(match|fit)|(wasn|isn)['’]?t (quite )?(the )?right (fit|match)|(was|is) not (quite )?(the )?right (fit|match)|(not|n['’]t) (feel|think|believe) (it|this|that)\w* (is|was|would be) (the |a )?(right|good) (match|fit)",
    r"(does|do) not (meet|match|align|fit)\w* (our|the) (requirement|need|profile|criteria)|(haven|have)['’]?t met the requirements|not (strong|good) enough to move forward",
    r"not the outcome you (were|had been) hoping for|do not see any possibility",
    r"(will|would) not be (able )?to (consider|proceed|continue|take|move|offer)\w* (your|the|this|you|with you|further)|will not be taking your application further|not (be )?taking (your|the) application (any )?further|have concluded that",
    r"(unfortunately|regrettably|sadly).{0,80}your (application|candidacy|profile).{0,60}(not|unable|declined|rejected|unsuccessful)",
    r"(unfortunately|regrettably|sadly).{0,40}\bwe (will|can|could|are going to|have to|must|are unable to) ?(not|n['’]t)?.{0,20}(proceed|continue|consider|move forward|invite|pursue|progress)",
    r"\b(declin|reject|unsuccessful)\w* (your|the) (application|candidacy)|your (application|candidacy) (was|has been|is|will be) (unsuccessful|declined|rejected|not successful)|in the next (stage|phase|round) of (our|the) (selection|process)",
    r"choose to pursue (other|another)|pursue other candidates|(won['’]?t|will not|not) be (progressing|proceeding|pursuing|continuing) (with )?(your|the) (application|candidacy)",
    # --- Dutch / Scandinavian / Polish / French / Spanish --------------------------------
    r"niet in aanmerking komt|tegenkandidaten|andere kandidaten|niet verder (gaan|te gaan|in de)|niet door naar|geen (match|vervolg)|besloten verder te gaan met|beter aansluiten|helaas .{0,60}(niet|geen)",
    r"(afwijz|afgewezen|niet geselecteerd|andere sollicitant)\w*",
    r"inte gått vidare|inte (går|kommer) vidare|valt att gå vidare med|gå vidare med andra|ikke gå videre|ikke går videre|ikke komme videre",
    r"nie będziemy kontynuować|zdecydowaliśmy się kontynuować rozmowy z (innymi|kandydatami)",
    r"malheureusement.{0,80}(pas (retenu|donné suite|sélectionn)|ne peut|ne pouvons)",
    r"(no hemos podido|lamentamos|lamentablemente).{0,80}(continuar|seleccion|candidatura|proceso)",
]
DECISION_RE = [re.compile(p, re.I) for p in DECISION]

# --------------------------------------------------------------------------------------------
# Tier 2: a regret phrase AND a negative outcome in the SAME sentence ("leider ... nicht ...").
# --------------------------------------------------------------------------------------------
REGRET = re.compile(r"\b(leider|bedauer\w*|tut uns leid|zu unserem bedauern|unfortunately|regret\w*|sorry|sadly|helaas|tyvärr|dessverre|niestety|malheureusement|lamentablemente)\b", re.I)
OUTCOME_NEG = re.compile(r"\b(entschieden|decided|nicht|kein\w*|ablehn\w*|absag\w*|andere[rnms]?|besetz\w*|vergeben|negativ\w*|not|no longer|never|cannot|can['’]?t|won['’]?t|unable|other|another|closed|filled|declin\w*|reject\w*|niet|geen|inte|ikke|pas|ne|non|andra|annan|andre)\b", re.I)

# --------------------------------------------------------------------------------------------
# Sentence-level vetoes: hypothetical / action requests / delays / scheduling / mass-mail apologies
# --------------------------------------------------------------------------------------------
CONDITIONAL = re.compile(r"(?<!auch )(?<!even )(?<!selbst )\bwenn\b|\bfalls\b|\bsofern\b|\bsobald\b|as soon as|\bnachdem\b|\bsollte\w*\b|(?<!even )\bif\b|\bshould\b|\bin case\b|\bonce\b", re.I)
VETO = re.compile(
    r"zugestellt|nicht zeigen|angezeigt|unterstützt keine|html|newsletter|abmelden|unsubscribe|\bmay\b|with everyone|mit jedem|jedem einzelnen|ohne (diesen|diese|den|die|das|dies)\b|without (this|these|completing)|\bunless\b|\bsolange\b|\buntil\b|nicht weiter bearbeiten|möglicherweise|vielleicht|eventuell|\bmight\b|may have|could have|\botherwise\b|delete your data|your data|datenschutz|gdpr|einverständnis|do not share this e-?mail|deel deze e-?mail|persönlichkeitstest|personality test|nur noch ein schritt|bitte (laden|senden|bestätigen|füllen)|"
    r"please (complete|upload|submit|confirm|take)|verzögert sich|verzögert|delay\w*|"
    r"(respond|reply|answer|get back) to (every|each|all)|(every|each) (single )?(candidate|applicant)|jede[rn]? (einzelne[nr]? )?(bewerber|kandidat)\w* (zu )?(antworten|beantworten)|"
    r"unable to (respond|reply|answer)|not (be )?able to (personally )?(respond|reply|answer)|"
    r"reschedul|verschieb|nochmals verschoben|cancel(l)?ed? (the |your )?(interview|call|meeting|appointment)|"
    r"(keep|halten) (you|dich|sie) (in mind|im blick|auf dem laufenden)", re.I)
SCHEDULING = re.compile(r"(\btermin\w*|\buhr\b|\bslot\b|kalender|calendar|zeitfenster|appointment|urlaub|abwesen|vacation|out of office|büro)", re.I)
ACTION_REQUEST = re.compile(r"(nur noch ein schritt|persönlichkeitstest|personality test|to move forward with your application,? we|um (mit )?deiner bewerbung fortzufahren|"
                            r"please (complete|upload|submit|fill)|bitte (laden|füllen|vervollständigen|bestätigen)|assessment link|"
                            r"complete (the|this|your) (assessment|test|questionnaire|profile))", re.I)
JOBISH = re.compile(r"(bewerbung|bewerber|application|applying|applicant|candidate|candidacy|stelle\b|position|vacancy|\brole\b|sollicitatie|vacature|ansökan|candidature|kandidat|recruit|hiring|rekrut|\bjob\b|sökande|\bapplied\b|\bapply\b|solicitud|puesto|vacante|tjänst|aplikac|interview|assessment|anstellung|kandidatenprofil|candidate profile|vorstellungsgespräch)", re.I)
FRAME = re.compile(r"(mitteilen|informieren|benachrichtigen|inform you|let you know|wir müssen|we have to|we must|dass wir|that we|zu unserem bedauern|bedauern wir|regret)", re.I)
INVITATION = re.compile(r"(laden wir (sie|dich)|einladung|wir möchten (sie|dich) .{0,30}einladen|invite you|invitation|interview with|vorstellungsgespräch|kennenlerngespräch)", re.I)

QUOTE_CUT = re.compile(
    r"(\n>|\bOn .{5,80} wrote:|\bAm .{5,80} schrieb|\bschrieb am\b|-{3,}\s*(Original|Ursprüngliche|Weitergeleitete|Forwarded)|"
    r"\bVon:\s.{0,80}\bGesendet:|\bFrom:\s.{0,80}\bSent:|\bGesendet:\s.{0,40}\bVon:|_{5,})", re.I)
# Substrings that identify the user's own address/name in a From header (mail the user sent is never a rejection).
# Set JOBTRACKER_USER_HINTS="yourname,yourdomain.com" (comma separated).
USER_HINTS = [h.strip().lower() for h in os.environ.get("JOBTRACKER_USER_HINTS", "").split(",") if h.strip()]


def _strip_quoted(text: str):
    m = QUOTE_CUT.search(text)
    return (text[:m.start()], text[m.start():]) if m else (text, "")


def _sentences(text: str):
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"This email was intended for .{0,400}?Learn why we included this\.?", " ", text, flags=re.S)
    text = re.sub(r"-{5,}", ". ", text)
    for s in re.split(r"(?<=[.!?])(?<!\d\.)\s+|\s{2,}|\s[-*•]\s", text):  # never split after a date like "28.07."
        s = s.strip()
        if 15 <= len(s) <= 700:
            yield s


def _vetoed(s: str) -> bool:
    if SCHEDULING.search(s) and not re.search(r"bewerbung|application|candidacy|stelle|position|bewerber", s, re.I):
        return True  # appointment talk ("Absage des Termins", "reschedule") is not a decision on the candidacy
    return bool(VETO.search(s) or CONDITIONAL.search(s))


APPLIED_REF = re.compile(r"(your (application|candidacy|profile|cv|resume)|you applied|applied (for|to|at)|deine[rn]? bewerbung|ihre[rn]? bewerbung|dein profil|ihr profil|"
                         r"für die (stelle|position)|auf die (stelle|position)|jouw sollicitatie|je sollicitatie|uw sollicitatie|din ansökan|din søknad|twoja aplikacj|votre candidature|tu solicitud|su solicitud)", re.I)
INTERVIEW_INVITE = re.compile(
    r"(\blad(en|e) (wir )?(sie|dich|euch) (\w+ ){0,3}(zu|zum) (einem |einer |unserem |unserer )?(\w+ )?(gespräch|interview|kennenlern|call|termin|vorstellung)|"
    r"invite you (for|to) (an? |the |our |your )?(\w+ ){0,3}(interview|call|meeting|conversation|chat|assessment)|(you['’]?re|you are|sie sind|du bist) (cordially )?(invited|eingeladen)\b.{0,60}(interview|gespräch|assessment|call|kennenlern|test)|"
    r"einladung zum (online-?)?assessment|zum online-?assessment eingeladen|"
    r"laden wir (sie|dich|euch) .{0,80}(gespräch|interview|termin|kennenlern|call|teams|zoom)|einladung zum (gespräch|interview|vorstellungsgespräch|kennenlern)|"
    r"einladung zu (einem|einer|unserem)\b.{0,30}(gespräch|interview|call|kennenlern)|invite you to (an? |the |our )?(first |second |initial )?(interview|call|meeting|conversation|chat|assessment)|"
    r"schedule (a|an|your) (call|interview|chat|meeting|time)|termin\w* .{0,30}(vereinbaren|buchen|auswählen|bestätigen)|book (a|your) (slot|time|call)|select a (time|slot)|"
    r"(freuen uns|happy|pleased|delighted) .{0,40}(einladen|invite|kennenzulernen|to meet you|to speak with you))", re.I)
NEGATION = re.compile(r"(\bnot\b|n['’]t\b|\bnicht\b|\bkein\w*|\bunable\b|\bleider\b|unfortunately|\bohne\b)", re.I)
MAX_SENTENCE_INDEX = 25  # a rejection states the decision near the top; deep in the text it is probably boilerplate


def classify(frm: str, subject: str, body: str, user_hints=None) -> dict:
    """PRECISION FIRST: REJECTION is returned only when we are confident; everything doubtful is UNCLEAR.
    Never auto-file UNCLEAR mail -- a false positive hides a real email (interview invite, offer, ...)."""
    if any(h in (frm or "").lower() for h in (user_hints or USER_HINTS)):
        return dict(verdict="NOT_REJECTION", sentence="", why="sent by the user")
    own, quoted = _strip_quoted(body or "")
    if not JOBISH.search((subject or "") + " " + own[:1500]):
        return dict(verdict="NOT_REJECTION", sentence="", why="not job related")
    sents = list(_sentences(own))

    # message-level context: anything in the sender's own text that says "this is not (only) a rejection"
    invite = next((x for x in sents if INTERVIEW_INVITE.search(x) and not NEGATION.search(x)), None)
    action = ACTION_REQUEST.search(own)
    context_block = ("message also invites to an interview" if invite
                     else "message asks the candidate to act" if action else "")

    # Tier 1: a specific decision phrase in one clean sentence near the top of the message
    for i, s in enumerate(sents):
        for rx in DECISION_RE:
            m = rx.search(s)
            if m and not _vetoed(s):
                why = f"decision phrase {m.group(0)[:50]!r}"
                if context_block:
                    return dict(verdict="UNCLEAR", sentence=s[:260], why=why + f" BUT {context_block}")
                if not APPLIED_REF.search((subject or "") + " " + own[:3000]):
                    return dict(verdict="UNCLEAR", sentence=s[:260], why=why + " BUT the message never refers to the user's own application")
                if i > MAX_SENTENCE_INDEX:
                    return dict(verdict="UNCLEAR", sentence=s[:260], why=why + " BUT deep in the text (boilerplate?)")
                return dict(verdict="REJECTION", sentence=s[:260], why=why, confidence="high")
    # Tier 2 (generic "regret + negative outcome"): never a REJECTION on its own, only a pointer for a human
    for s in sents:
        if REGRET.search(s) and OUTCOME_NEG.search(s) and not _vetoed(s) \
                and (FRAME.search(s) or re.search(r"bewerbung|application|candidacy|stelle|position", s, re.I)) \
                and not (SCHEDULING.search(s) and not re.search(r"bewerbung|application|candidacy", s, re.I)):
            return dict(verdict="UNCLEAR", sentence=s[:260], why="generic regret + negative wording, no specific decision phrase")
    # decision phrase only in the subject / only in quoted text / only in a vetoed sentence
    if any(rx.search(subject or "") for rx in DECISION_RE):
        return dict(verdict="UNCLEAR", sentence=(subject or "")[:260], why="decision phrase only in the subject")
    for s in _sentences(quoted):
        if any(rx.search(s) for rx in DECISION_RE):
            return dict(verdict="UNCLEAR", sentence=s[:260], why="decision phrase only in quoted text")
    for s in sents:
        if any(rx.search(s) for rx in DECISION_RE) and _vetoed(s):
            return dict(verdict="UNCLEAR", sentence=s[:260], why="decision phrase next to conditional/pending wording")
    return dict(verdict="NOT_REJECTION", sentence="", why="no decision sentence")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--emails", required=True)
    ap.add_argument("--bodies", required=True)
    ap.add_argument("--show", default="", help="only print this verdict")
    a = ap.parse_args()
    emails, bodies = json.load(open(a.emails)), json.load(open(a.bodies))
    c = collections.Counter()
    for e in emails:
        r = classify(e["frm"], e["subject"], bodies.get(e["id"], ""))
        c[r["verdict"]] += 1
        if not a.show or r["verdict"] == a.show:
            print(f"{r['verdict']:13} {e['frm'].split('<')[0][:22]:22} | {e['subject'][:50]} | {r['sentence'][:110]}")
    print(dict(c))
