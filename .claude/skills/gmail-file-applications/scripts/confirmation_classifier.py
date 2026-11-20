#!/usr/bin/env python3
"""Sentence-level classifier for job-application *confirmation* emails ("we received your application").

PRECISION FIRST (same principle as the rejection classifier): filing a mail out of the inbox hides it, so
CONFIRMATION is returned only when we are sure it is a plain acknowledgement. Anything that also contains
a rejection, an interview invitation, a request for the candidate to act, or a question to the candidate is
UNCLEAR and stays in the inbox for the user.

    from confirmation_classifier import classify_confirmation
    r = classify_confirmation(frm, subject, body)   # -> {"verdict", "sentence", "why", "easyapply"}

verdict  CONFIRMATION | UNCLEAR | NOT_CONFIRMATION
easyapply True for LinkedIn Easy Apply receipts ("Alex, your application was sent to <Company>").
"""
import os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gmail-file-rejections", "scripts"))
from rejection_classifier import (classify as classify_rejection, _sentences, _strip_quoted, INTERVIEW_INVITE,  # noqa: E402
                                  NEGATION, JOBISH, USER_HINTS)

# One sentence that acknowledges the application. (DE / EN)
CONFIRM = [re.compile(p, re.I) for p in [
    r"\b(we|wir)\b.{0,30}\b(have |'ve |haben )?(successfully )?(received|erhalten)\b.{0,40}\b(your|deine|ihre)\b.{0,30}\b(application|bewerbung|unterlagen|documents)",
    r"\b(your|deine|ihre)\b.{0,20}\b(application|bewerbung|unterlagen)\b.{0,60}\b(has been|was|is|wurde|ist|ist bei uns)?\s*(successfully |erfolgreich )?(received|submitted|sent|eingegangen|eingereicht|übermittelt|erhalten|angekommen)",
    r"thank(s| you)( very much| so much)? for (your application|applying|your interest in (applying|the position))",
    r"(vielen|herzlichen) dank für (deine|ihre|die|eure) bewerbung",
    r"bestätigen (wir )?(dir |ihnen )?(hiermit |gerne )?(den )?(eingang|erhalt)",
    r"eingangsbestätigung|confirmation of (receipt|your application)|application (received|confirmation|submitted)",
    r"bewerbung (ist )?(bei uns )?(eingegangen|angekommen)",
    r"(deine|ihre) bewerbung (wurde )?(erfolgreich )?(an .{1,60} )?(gesendet|abgeschickt|übermittelt)",
    r"your application was sent to",
    r"eingang (der|ihrer|deiner) (online-?)?bewerbung|bewerbungsunterlagen (dankend )?erhalten|acknowledge receipt of your application|"
    r"freuen uns (sehr )?über (deine|ihre) bewerbung|bewerbung über indeed:",
    r"\b(wir|we)\b.{0,30}\b(haben|have)\b.{0,10}\b(deine|ihre|your) (bewerbung|application)\b.{0,150}\b(erhalten|received)\b",   # long job titles between the words
    r"(be)?dank\w*\b.{0,25}\b(für|fuer)\b.{0,25}\b(bewerbung|zusendung)",                       # Danke für deine Bewerbung / bedanken uns für Ihre Bewerbung
    r"thank(s| you)\b.{0,30}\b(for|you for)\b.{0,15}\b(submitting|sending|your)\b.{0,15}\b(application|cv|resume)",  # thank you for submitting your application / Thanks a lot for your application
    r"thank(s| you)\b.{0,15}\bfor your interest in\b.{0,60}\b(joining|working|our (company|team|organisation)|the (position|role|job)|as an? )",
    r"(freuen|freue) (uns|mich) (sehr )?über (dein|ihr|euer) interesse",
    r"(kopie|copy) (deiner|ihrer|of your) (bewerbung|application)|danke für die erstellung (deines|ihres) profils",
    r"(wir werden|we will|we(['’]ll)?) (deine|ihre|die|your) (unterlagen|bewerbungsunterlagen|application|documents)\b.{0,25}\b(prüfen|review|check)|(currently|derzeit) (reviewing|prüfen) your (profile|application)|"
    r"vielen dank für (die )?zusendung (deiner|ihrer|ihre|deine) bewerbung|(wir haben|haben wir) (deine|ihre) bewerbung (bearbeitet|zur kenntnis genommen)",
]]
# Easy Apply: LinkedIn receipt
EASYAPPLY = re.compile(r"(your application was sent to|ihre bewerbung wurde an .{1,60} gesendet|application sent to)", re.I)

# Anything asking the candidate to do something, or posing a question -> never file automatically.
ACTION = re.compile(
    r"((please|bitte|kindly)\s+(\w+\s+){0,3}(send|provide|attach|upload|fill|complete|reply|respond|schedule|book|confirm|verify|submit|übersend|schick|sende|laden|füll|vervollständig|bestätig|antwort|buch|wähl|select|click|klick)|"
    r"((could|can|would) you|kannst du|könntest du|können sie|könnten sie|würden sie|würdest du)\b.{0,60}\b(send|provide|attach|upload|confirm|verify|complete|fill|reply|respond|share|schick\w*|send\w*|übermitt\w*|mitteil\w*|bestätig\w*|ausfüll\w*|hochlad\w*|nachreich\w*|antwort\w*|angeben|nennen|beantwort\w*)|"
    r"(verify|confirm|bestätig\w+) (your|deine|ihre) (e-?mail|address|account|konto)|"
    r"(complete|finish|vervollständig\w+) (your|the|deine|ihr\w*) (profile|application|bewerbung|assessment|test|questionnaire|survey)|"
    r"\b(assessment|tests?|aptitude|persönlichkeitstest|coding challenge|video interview|videointerview|fragebogen|questionnaire)\b|"
    r"(deadline|\bfrist\b|bis (spätestens )?\d{1,2}\.\d{1,2}\.)|(missing|fehlende?n?|unvollständig|incomplete)\b|"
    r"salary expectation|gehaltsvorstellung|verfügbarkeit|availability|notice period|kündigungsfrist|"
    r"(your|deine|ihre)\s+(application|bewerbung)\s+(is|ist)\s+(incomplete|unvollständig))", re.I)
# Recall-oriented veto: wording that appears in rejections / status changes. A rejection the rejection
# classifier does not recognise must still never be filed as a mere receipt, so ANY of this -> stays in inbox.
RISK = re.compile(
    r"\b(unable|not able|cannot|can[\'’]?t|won[\'’]?t|will not|do not|don[\'’]?t|nicht möglich|nur möglich|kein\w*)\b|"
    r"\b(however|jedoch|allerdings|dennoch|nevertheless|aber leider|but unfortunately)\b|"
    r"\b(requires?|required|proficien\w*|sprachniveau|sprachkenntnisse|deutschkenntnisse|level of (german|dutch|english))\b|"
    r"\b(benötigen|benötigt|erforderlich|voraussetzung)\b.{0,60}\b(sprach|deutsch|englisch|niveau|kenntnisse|erfahrung|qualifikation|profil|studium|abschluss)\w*|"
    r"(engere|engeren|engsten) (wahl|auswahl|kreis)|shortlist\w*|"
    r"(einlad\w*|invit\w*|interview\w*|gespräch\w*|vorstellungs\w*|kennenlern\w*|\btermin\w*|appointment|\bschedul\w*|video ?call|\bzoom\b|teams[- ]?(meeting|einladung|call)|telefonat|telefon\w*)|"
    r"(unfortunately|leider|regret|bedauer\w*|sorry|zu unserem bedauern|tut uns leid|sadly|helaas|tyvärr|malheureusement|"
    r"\bfilled\b|discontinu\w*|besetzt|vergeben|abgebrochen|eingestellt|withdrawn|\bcancel\w*|"
    r"other (candidates|applicants)|andere[nr]? (kandidat|bewerber)|kandidat:innen|bewerber:innen|weiterzuführen|weiterzuverfolgen|"
    r"talent ?pool|keep (your|an) (profile|cv|eye)|future (role|opportunit|vacanc|position)|zukünftig\w*|"
    r"nicht leicht ?gefallen|entschieden|\bdecided\b|no match|don['’]?t have a match|not (a )?(strong )?match|"
    r"(speichern|aufbewahren|retain|store) (wir )?(deine|ihre|your)|in unserer (talent)?datenbank|"
    r"not (be )?(moving|selected|proceed)|nicht (weiter|berücksichtig)|update on your application|application update|neuigkeiten zu)", re.I)
# Boilerplate that trips RISK/ACTION but never signals a decision or a request (measured on 400 filed receipts, 2026-10-08):
# signatures ("Telefon: +49 ..."), "please do not reply", "do not hesitate to contact us", "keine Nachricht verpassen", "benötigen etwas Zeit",
# "leiten Sie diese E-Mail nicht weiter". Only these exact phrases are removed before the veto checks; decision wording is untouched.
BENIGN = re.compile(
    r"(please )?do ?n[o'’]t hesitate|(please )?do not reply( to this e-?mail)?|bitte (nicht )?(auf diese e-?mail )?antworte[n]?( sie)? nicht|don[’']t (forget|miss|worry)|do not forget|you don[’']t have to do anything|"
    r"we do not cover travel expenses|telefon\w*:?\s*[+(\d][\d\s()/+\-|.]{5,}|(mobil|fax|telefax|tel\.?)\w*:?\s*[+(\d][\d\s()/+\-|.]{5,}|"
    r"kandidat:innen(profil| zu verbessern)|damit (du|sie|ihr) keine (nachricht|e-?mail)\b[^.]{0,50}|damit keine nachricht verloren geht|noch keine konkrete aussage|"
    r"(teilen|leiten) sie (diese|sie|die) e-?mail nicht (und leiten sie sie nicht )?weiter|bitte teilen sie diese e-?mail nicht und leiten sie sie nicht weiter|"
    r"e-?mail transmission cannot be guaranteed[^.]*|internet kein sicheres kommunikationsmedium|"
    r"(benötigen|brauchen) (wir |noch )?(allerdings |dafür |etwas |ein wenig |noch etwas |noch ein wenig )*(zeit|geduld)|dafür benötigen wir allerdings ein wenig zeit|"
    r"(time|zeit) (is |ist )?(required|benötigt) to (process|review)|will require a little more time|longer time required|"
    r"bitte beachte jedoch, dass dies bei positionen mit vielen bewerbungen[^.]*|melde dich dennoch sehr gerne|sollten dennoch fragen offen bleiben|keep an eye on (your|the) (inbox|spam)|spam-?ordner im blick",
    re.I)
# Platform receipts (Indeed/Stepstone/LinkedIn) carry long footers with "interview tips" / "similar jobs": judge only their first lines.
PLATFORM_RECEIPT = re.compile(r"(bewerbung über indeed|ihre bewerbung wurde weitergeleitet|your application (for .{0,150} )?has been (successfully )?sent|your application was sent to)", re.I)
MARKETING = re.compile(r"(unsubscribe|abmelden|newsletter|job ?alert|jobs? (for|für) you|neue jobs|ähnliche (jobs|stellen)|similar jobs|"
                       r"recommended jobs|jobempfehlung|stellenempfehlungen|these jobs|new jobs|weekly|angebote|rabatt|sale\b)", re.I)


def classify_confirmation(frm: str, subject: str, body: str, user_hints=None) -> dict:
    out = lambda v, why, s="", easy=False: dict(verdict=v, sentence=s[:260], why=why, easyapply=easy)
    low_from = (frm or "").lower()
    if any(h in low_from for h in (user_hints or USER_HINTS)):
        return out("NOT_CONFIRMATION", "sent by the user")
    own, _quoted = _strip_quoted(body or "")
    text = (subject or "") + " " + own
    if not JOBISH.search(text[:1500]):
        return out("NOT_CONFIRMATION", "not job related")
    easy = ("linkedin.com" in low_from) and bool(EASYAPPLY.search(subject or ""))

    sents = list(_sentences(own))
    hit = next((x for x in [subject or ""] + sents[:30] for rx in CONFIRM if rx.search(x)), None)
    if hit is None:   # job titles contain " - " / "(f/m/d)", which the sentence splitter cuts in two: try the running text too
        flat = re.sub(r"\s+", " ", own[:900])
        hit = next((flat[:260] for rx in CONFIRM if rx.search(flat)), None)
    if hit is None:
        return out("NOT_CONFIRMATION", "no acknowledgement sentence")

    # Everything below can only DOWNGRADE to UNCLEAR: never hide a message that may need the user.
    r = classify_rejection(frm, subject, body)
    if r["verdict"] != "NOT_REJECTION":
        return out("UNCLEAR", f"also looks like a rejection/decision ({r['why'][:50]})", hit, easy)
    invite = next((x for x in sents if INTERVIEW_INVITE.search(x) and not NEGATION.search(x)), None)
    if invite:
        return out("UNCLEAR", "contains an interview invitation", invite, easy)
    if PLATFORM_RECEIPT.search(text[:400]) and re.search(r"(indeed|stepstone|linkedin)", low_from):
        text, own = text[:700], own[:700]       # footer tips are not part of the message
    text, own_checked = BENIGN.sub(" ", text), BENIGN.sub(" ", own)
    risk = RISK.search(text)
    if risk and not easy:
        return out("UNCLEAR", f"risk wording {risk.group(0)[:30]!r} (could be a rejection/status change)", hit, easy)
    m = ACTION.search(own_checked)
    if m and not easy:
        return out("UNCLEAR", f"asks the candidate to do something ({m.group(0)[:40]!r})", hit, easy)
    if MARKETING.search(own_checked[:2500]) and not easy and not re.search(r"eingangsbestätigung|application (received|confirmation)", text, re.I):
        return out("UNCLEAR", "contains newsletter/job-alert wording", hit, easy)
    if len(body or "") >= 1800 and not easy:  # bodies are fetched truncated (3000 chars): a long mail may hide more
        return out("UNCLEAR", "long message (more than a short receipt, may continue past what was read)", hit, easy)
    return out("CONFIRMATION", "acknowledgement sentence, nothing else", hit, easy)


if __name__ == "__main__":
    import argparse, collections, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--emails", required=True)
    ap.add_argument("--bodies", required=True)
    ap.add_argument("--show", default="")
    a = ap.parse_args()
    emails, bodies = json.load(open(a.emails)), json.load(open(a.bodies))
    c = collections.Counter()
    for e in emails:
        r = classify_confirmation(e["frm"], e["subject"], bodies.get(e["id"], ""))
        c[r["verdict"] + ("+easy" if r["easyapply"] else "")] += 1
        if not a.show or r["verdict"] == a.show:
            print(f"{r['verdict']:16}{'E' if r['easyapply'] else ' '} {e['frm'].split('<')[0][:22]:22} | {e['subject'][:50]} | {r['why'][:60]}")
    print(dict(c))
