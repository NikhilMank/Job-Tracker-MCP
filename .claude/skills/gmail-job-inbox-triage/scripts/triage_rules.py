#!/usr/bin/env python3
"""The classification rules of triage_inbox.py, importable so they can be tested (test_triage.py).

    from triage_rules import triage_one
    bucket, note = triage_one(email_dict, body)     # bucket is None for mail that is not about the user's job search

Buckets: SHORTLISTED | NEEDS_YOU | REJECTION | CONFIRM_EASY | CONFIRM | DOUBTFUL | UNCLASSIFIED | STALE_PROFILE   (see triage_inbox.py)
Design rule (learned the hard way): a job-related mail from a company must NEVER vanish without a trace.
If no rule recognises it, it lands in UNCLASSIFIED and is listed for a human, not silently skipped.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(SK, "gmail-file-rejections", "scripts"))
sys.path.insert(0, os.path.join(SK, "gmail-file-applications", "scripts"))
from rejection_classifier import (classify as classify_rejection, INTERVIEW_INVITE, NEGATION, JOBISH, CONDITIONAL, APPLIED_REF,  # noqa: E402
                                  _sentences, _strip_quoted, USER_HINTS)
from confirmation_classifier import classify_confirmation, MARKETING  # noqa: E402

# Strong, explicit requests only. Generic phrases ("können Sie Fragen stellen", "kannst du", "Frist", "please reply") are far
# too common in receipts and newsletters; those mails go to CONFIRM/DOUBTFUL instead.
STRONG_ACTION = re.compile(
    r"(persönlichkeitstest|personality test|nur noch ein schritt|online-?assessment|coding challenge|take-?home|"
    r"(please|bitte|kindly)\s+(\w+\s+){0,3}(upload|submit|verify|laden .{0,20}hoch|bestätig\w+|übersend\w+|complete the|füll\w+)|"
    r"kindly ask you to provide|(provide|send|upload) (a|your|the) (certificate|zeugnis|nachweis|documents?)|"
    r"fehlende dokumente (senden|nachreichen)|salary expectation|gehaltsvorstellung|"
    r"complete and submit your (job )?application|saved a draft of your|continue to apply for the job|(passwort|password) (zu )?(vergeben|setzen|assign)|"
    r"vervollständige (dein|ihr)\w* (kandidatenprofil|profil)|complete your candidate profile)", re.I)
OFFER = re.compile(r"(job offer|offer letter|pleased to offer you|happy to offer you|we would like to offer you|arbeitsvertrag(?!es)|vertragsangebot|"
                   r"wir möchten (dir|ihnen|sie|dich) .{0,40}(angebot|vertrag|zusage)|congratulations|herzlichen glückwunsch)", re.I)
NOISE = re.compile(r"(stepstone\.de|jobagent|jobnotification|job-?notification|job-?alert|glassdoor|xing\.com|jobvector|newsletter|"
                   r"instaffo|talent ?rocket|efinancialcareers|workwise|noreply@.*careers|"
                   r"carbon\.talent|carbondata|careeralerts|talent@ibm|halian|safemind|joblead|digitale leute|find a job in germany)", re.I)

# Mail about the user's own process that does not say "application" (e.g. "Thanks for your interest in working as ...",
# or "Sie sind zum Online-Assessment eingeladen"). Used only for NEEDS_YOU / UNCLASSIFIED, never for filing.
ABOUT_ME_EXTRA = re.compile(r"(interest in (working|joining)|your interest in|ihr interesse|dein interesse|interesse an (einer|der) (anstellung|tätigkeit|stelle)|"
                            r"invited to|zum .{0,25}(interview|assessment|gespräch) eingeladen|first (video )?interview|candidate profile|kandidatenprofil|"
                            r"saved a draft of your|draft of your (job )?application)", re.I)
# A subject like this is never dropped silently, even if the body has no "job" word at all.
SUBJECT_FLAG = re.compile(r"(interview|einladung|invited|assessment|vorstellungsgespräch|kennenlern|your application|deine bewerbung|ihre bewerbung|bewerbung|zwischenstand|continue to apply)", re.I)
PLATFORM_NOISE = re.compile(r"(linkedin\.com|stepstone|glassdoor|xing\.com|indeed\.com|jobvector|instaffo|efinancialcareers|workwise|alignerr|airswift|talentrocket)", re.I)



# Positive replies (standing rule): star + label JobApplications/Shortlisted (stays in the inbox) + tracker status.
SHORTLIST_POS = re.compile(r"(in (die|der) (engere[nr]?|engste[nr]?) (auswahl|wahl)( gekommen| gezogen| aufgenommen| genommen)?|you(['’]ve| have) been shortlisted|you are shortlisted|"
                           r"(profil|bewerbung) hat uns (überzeugt|gefallen|beeindruckt)|(möchten|würden) (wir )?(sie|dich|euch) (gerne )?(persönlich )?kennenlernen|"
                           r"next (stage|round|step) (of|in) (the|our) (process|interview)|nächste(n)? (runde|phase|stufe) )", re.I)
# Automated process steps (anything that needs an action from the user gets NeedsAttention and stays in the inbox; replaces the
# "label only" rule): online assessments, aptitude /
# personality tests, questionnaires, coding-challenge platforms. They are sent to EVERY applicant, usually by a vendor (ELIGO, cut-e, Harver, Codility,
# HackerRank, TestGorilla, ...) with a username/link and a deadline. They are NOT a positive reply: no star, no Shortlisted label, but they are NEEDS_YOU
# (NeedsAttention label, inbox). The report mentions the deadline. A human interview invitation or a document/salary request still wins.
AUTO_ASSESS = re.compile(r"(zum (online-?)?assessment eingeladen|einladung zum (online-?)?assessment|online-?assessment|invited to (complete |take )?(an? |the )?(online )?(assessment|coding challenge|technical test)|"
                         r"persönlichkeitstest|personality (test|questionnaire)|fragebogen zum persönlichkeits|eignungstest|aptitude test|cognitive (ability )?test|situational judge?ment|"
                         r"(ihr|dein) benutzername lautet|your username is|passwort vergeben|assign (a )?password|coding challenge|online test|testlink)", re.I)
ASSESS_VENDOR = re.compile(r"(eligo|cut-?e\b|harver|codility|hackerrank|testgorilla|plum\.io|talentclear|retorio|hirevue|willo|sparkhire|vervoe|mettl|criteria|saville|assessment)", re.I)
# requests that need the user for real (documents, salary, e-mail confirmation) -- these stay NEEDS_YOU even next to a test
REAL_REQUEST = re.compile(r"((please|bitte|kindly)\s+(\w+\s+){0,3}(upload|verify|laden .{0,50}hoch|übersend\w+)|kindly ask you to provide|(provide|send|upload) (a|your|the) (certificate|zeugnis|nachweis|documents?)|(zeugnis|nachweis|unterlagen|dokumente)\\w*.{0,40}(hochladen|hoch\\b|nachreichen|übersenden)|"
                          r"fehlende dokumente|salary expectation|gehaltsvorstellung|saved a draft of your|complete your candidate profile|vervollständige (dein|ihr)\w* (kandidatenprofil|profil))", re.I)

# "We will delete your profile soon because of inactivity -- log in to keep it" (user: trash these). A mail that merely states a data-retention
# policy (receipts, rejections: "we delete your data after 6 months") has no imminence and no call to log in, so it is NOT matched.
STALE_TOPIC = re.compile(r"(inaktiv\w*|inactiv\w*|bevorstehende(n)? löschung|löschung (ihres|deines|ihrer|deiner) (profils|daten|kandidatenprofils)|deletion of your (profile|data|account)|"
                         r"(profile|profil|account|konto|data|daten|application data)\b.{0,60}\b(deleted|gelöscht|flagged for removal|removal|entfernt)|gdpr notification)", re.I)
STALE_IMMINENT = re.compile(r"(in \d+ (days?|tagen|wochen|weeks)|within \d+ (days?|weeks)|innerhalb von \d+ (tagen|wochen)|soon|bald|demnächst|bevorstehend\w*|upcoming|flagged for removal|"
                            r"due to inactivity|aufgrund (von |der )?inaktivität|wegen inaktivität|automatisch gelöscht|automatically (be )?deleted|will be (permanently )?(deleted|removed)|"
                            r"werden .{0,30}gelöscht|löschen wir (dein|ihr|ihre|deine))", re.I)
STALE_CTA = re.compile(r"(log ?in|sign in|anmelden|einloggen|login|reactivate|reaktivier\w*|keep (your|my) (profile|data)|profil (erhalten|behalten|aktiv)|aktiv bleiben|"
                       r"verlänger\w*|extend|bestätig\w* sie|confirm (that|your)|weiterhin (an einer zusammenarbeit )?interessiert|still interested|interessiert sind)", re.I)
CAREER_WORDS = re.compile(r"(career|karriere|recruit|talent|candidate|kandidat|bewerb|application|jobs?\b|portal|bewerber)", re.I)


def is_stale_profile_warning(frm, subj, own):
    text = subj + " " + own[:3000]
    head = subj + " " + own[:700]
    return bool(CAREER_WORDS.search(frm + " " + text) and STALE_TOPIC.search(head) and STALE_IMMINENT.search(text) and STALE_CTA.search(text))


# Consent / data-retention requests ("keep my data?", "we still store your data", "request for consent"): no application is involved, the user
# trashes them . Matched on subject + the first 300 chars only, so static
# retention sentences deep inside receipts and rejections never trigger it.
CONSENT_RETENTION = re.compile(r"(einverständnis\w*|request for consent|data retention|retention policy|(daten|data) (sind |is |are )?(noch |still )?(gespeichert|stored)|"
                               r"keep (considering you|your information|your data)|extend permission|weiter(hin)? .{0,20}(bewerber)?pool|talent (pool|community) .{0,30}(erhalten|stay))", re.I)
# Interview appointment changes ("neue Uhrzeit", "Abgesagtes Ereignis", "Updated invitation", "Rescheduling your interview"): the user must see them
# and the notes in data/shortlisted.md need the new time (a changed interview time must not go unreported).
RESCHEDULE = re.compile(r"((gespräch|interview|termin|kennenlern\w*).{0,60}(neue uhrzeit|neuer termin|verschoben|verlegt|abgesagt|rescheduled|cancel+ed)|"
                        r"(neue uhrzeit|abgesagtes ereignis|canceled event|cancelled event|updated invitation|rescheduling (your|the) interview|reschedul\w+ .{0,30}interview))", re.I)
# Accounts the portal created for the user and application-feedback surveys: receipts, file them .
ACCOUNT_CREATED = re.compile(r"(profil auf unserer karriereseite erstellt|konto auf der .{0,40}karriereseite (wurde )?erstellt|(your|ihr|dein) (candidate )?(account|profile|profil) (has been|was|wurde) (created|erstellt)|"
                             r"successfully created (a|your) (candidate )?(profile|account))", re.I)
APPLICATION_SURVEY = re.compile(r"(feedback on our application process|anonymous feedback|candidate (experience )?survey|umfrage zu (deiner|ihrer) bewerbung|feedback zum bewerbungsprozess|"
                                r"submit feedback)", re.I)
CAREER_SENDER = re.compile(r"(career|karriere|recruit|talent|bewerb|hr@|jobs@|hiring|personal)", re.I)

CONFIRM_BUTTON = re.compile(r"(confirm_application|ohne bestätigung|bestätigung zur verifikation|bestätigen der bewerbung|confirm your (e-?mail|application)|click (the|this) link to (confirm|complete))", re.I)
NEGATION_DECISION = re.compile(r"(leider|unfortunately|bedauern|regret|nicht berücksichtigen|not (be )?moving forward|absage)", re.I)


def triage_one(e, body):
    frm, subj = e["frm"], e["subject"]
    low = frm.lower()
    if any(h in low for h in USER_HINTS):
        return None, ""
    own, _ = _strip_quoted(body)
    if is_stale_profile_warning(frm, subj, own) and not NOISE.search(low) and classify_rejection(frm, subj, body)["verdict"] != "REJECTION" \
            and not INTERVIEW_INVITE.search(own[:2500]):
        return "STALE_PROFILE", "profile/data deletion warning for inactivity (log in to keep it) -> trash"
    if RESCHEDULE.search(subj) and not NOISE.search(low):
        return "NEEDS_YOU", "interview time change / cancellation -> tell the user, update data/shortlisted.md (new time)"
    if CONSENT_RETENTION.search(subj + " " + own[:300]) and CAREER_WORDS.search(frm + " " + subj + " " + own[:600]) and not NOISE.search(low) \
            and classify_rejection(frm, subj, body)["verdict"] != "REJECTION" and classify_confirmation(frm, subj, body)["verdict"] != "CONFIRMATION" \
            and not INTERVIEW_INVITE.search(own[:2500]):
        return "STALE_PROFILE", "consent / data-retention request, no application involved -> trash"
    if not JOBISH.search(subj + " " + body[:1500]) and not SUBJECT_FLAG.search(subj) and not ACCOUNT_CREATED.search(own[:600]) and not APPLICATION_SURVEY.search(own[:800]):
        return None, ""   # private mail / shopping / newsletters with no job wording at all
    sents = list(_sentences(own))
    about_me = bool(APPLIED_REF.search(subj + " " + own[:3000]) or ABOUT_ME_EXTRA.search(subj + " " + own[:3000])) \
        and not NOISE.search(low) and not MARKETING.search(own[:2500])
    invite = next((x for x in sents if INTERVIEW_INVITE.search(x) and not AUTO_ASSESS.search(x) and not NEGATION.search(x) and not CONDITIONAL.search(x)), None) if about_me else None
    rej = classify_rejection(frm, subj, body)
    con = classify_confirmation(frm, subj, body)
    act = STRONG_ACTION.search(own) if about_me and not ACCOUNT_CREATED.search(own[:600]) else None   # "please complete your profile" in a welcome mail is not a request
    offer = (OFFER.search(subj + " " + own[:1500]) if rej["verdict"] != "REJECTION" else None) if about_me else None   # a match object, never a bool (the SHORTLISTED line calls .group)
    if (AUTO_ASSESS.search(subj + " " + own[:2500]) or (ASSESS_VENDOR.search(low) and re.search(r"(einladung|invit|benutzername|username|passwort|password|link)", subj + " " + own[:1500], re.I))) \
            and about_me and rej["verdict"] != "REJECTION" and not REAL_REQUEST.search(own) and not invite:
        return "NEEDS_YOU", "automated assessment / test step the user must complete -> NeedsAttention, stays in inbox (mention task + deadline in the report)"
    positive = (SHORTLIST_POS.search(subj + " " + own[:2500]) if about_me else None)
    # A positive reply (interview/assessment invitation, shortlisted, offer) wins over NEEDS_YOU: star + label + tracker status.
    if (invite or offer or positive) and rej["verdict"] != "REJECTION" and con["verdict"] != "CONFIRMATION":
        why = ("interview invitation" if invite else "offer" if offer else "shortlisted / next stage")
        return "SHORTLISTED", why + ": " + (invite or (positive.group(0) if positive else "") or (offer.group(0) if offer else ""))[:80]
    # NEEDS_YOU wins over everything else: never hide mail that wants something from the user. Marketing sender exempt.
    if act and rej["verdict"] != "REJECTION" and con["verdict"] != "CONFIRMATION":
        return "NEEDS_YOU", f"asks you to act ({act.group(0)[:30]!r})"
    # "confirm your application or it is deleted" is a to-do for the user, not a rejection
    if about_me and CONFIRM_BUTTON.search(subj + " " + own[:3000]) and not NEGATION_DECISION.search(own[:3000]):
        return "NEEDS_YOU", "application incomplete until you confirm it (confirm link)"
    if rej["verdict"] == "REJECTION":
        return "REJECTION", rej["sentence"]
    if con["verdict"] == "CONFIRMATION":
        return ("CONFIRM_EASY" if con["easyapply"] else "CONFIRM"), con["sentence"]
    if (ACCOUNT_CREATED.search(own[:600]) or APPLICATION_SURVEY.search(own[:800])) and rej["verdict"] != "REJECTION" and not act:
        return "CONFIRM", "portal account created / application feedback survey -> receipt, file it"
    if con["verdict"] == "UNCLEAR" or rej["verdict"] == "UNCLEAR":
        return "DOUBTFUL", (con["why"] if con["verdict"] == "UNCLEAR" else rej["why"])
    if not PLATFORM_NOISE.search(low) and not NOISE.search(low) and not MARKETING.search(own[:2500]) \
            and (APPLIED_REF.search(subj + " " + own[:3000]) or SUBJECT_FLAG.search(subj)):
        # job-related, from a company / ATS, and no rule knows it: never leave it invisible
        return "UNCLASSIFIED", "no pattern matched -- read it (receipt? rejection? request?)"
    if CAREER_SENDER.search(frm) and JOBISH.search(subj + " " + body[:1500]) and not PLATFORM_NOISE.search(low) and not NOISE.search(low) and not MARKETING.search(own[:2500]):
        return "UNCLASSIFIED", "career/recruiting sender, no rule matched -- read it"
    return None, ""
