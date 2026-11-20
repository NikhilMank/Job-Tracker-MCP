#!/usr/bin/env python3
"""Regression tests for triage_rules.triage_one. Run: python test_triage.py (exit 1 on failure).
Every case is a REAL mail (anonymised to its key sentences) that the triage once dropped silently: an interview
invitation, an assessment deadline, a draft application, a rejection and several plain receipts. The rule behind them:
job-related mail from a company must land in SOME bucket, never vanish. Add a case whenever a mail slips through."""
import os; os.environ.setdefault("JOBTRACKER_USER_HINTS", "alex.example")  # the tester's own address
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage_rules import triage_one  # noqa: E402

M = lambda frm, subj: dict(id="x", frm=frm, subject=subj, date="", labels=["INBOX"])
CASES = [
    # (from, subject, body, expected bucket)  -- None = correctly ignored
    # GDPR footer "Sollte kein Abschluss eines Arbeitsvertrages erfolgen" is not an offer
    ("Acme SE <bewerbung@acme.example>", "Ihre Bewerbung - Eingangsbestätigung",
     "Sehr geehrter Herr Example, herzlichen Dank für Ihr Interesse an einer Mitarbeit in unserem Unternehmen. Sie haben sich bei uns für die Position 'SOFTWAREENTWICKLER (m/w/d) FOKUS KI' beworben. "
     "Aufgrund der Vielzahl der eingegangenen Bewerbungen wird die Bearbeitung einige Zeit in Anspruch nehmen, wir werden uns schnellstmöglich wieder mit Ihnen in Verbindung setzen. "
     "Der Schutz Ihrer persönlichen Daten ist uns ein besonderes Anliegen. Gemäß Art. 13 DS-GVO informieren wir Sie auf www.acme.example. Sollte kein Abschluss eines Arbeitsvertrages erfolgen, werden Ihre Daten unverzüglich gelöscht.",
     "DOUBTFUL"),   # was SHORTLISTED (offer); doubtful because of the risk word "kein" is fine, it gets read
    ("Globex <noreply@jobs.globex.com>", "Bestätigen der Bewerbung und Erstellen Ihres Karriereportal-Kontos",
     "Sehr geehrte/r Bewerber/in, Ihre Bewerbung ist bei uns eingegangen, herzlichen Dank! Zur Bearbeitung Ihrer Bewerbung benötigen wir eine Bestätigung zur Verifikation Ihrer Person. "
     "Bitte nutzen Sie hierfür den folgenden Link: https://jobs.globex.com//index.php?ac=confirm_application&code=x Bitte beachten Sie, dass wir ohne Bestätigung nicht mit der "
     "Bearbeitung fortfahren können und Ihre Bewerbung nach 21 Tagen gelöscht wird.", "NEEDS_YOU"),   # confirm-button mail, NOT a rejection
    ("Pat Recruiter <pat@acme-corp.example>", "Alex, you're invited to an interview with Acme!",
     "Hello Alex, Thanks for your interest in working as a AI Systems Engineer (f/m/d) at Acme. I am thrilled to invite you for your first video interview with Acme. "
     "Please select a moment of your choice from my calendar: Easybook link. Best regards, Jan", "SHORTLISTED"),
    ("Supportteam ELIGO <globex-supportteam@notify.eligo.de>", "Einladung zum Online-Assessment",
     "Guten Tag Alex Example, vielen Dank für Ihr Interesse an einer Anstellung bei der Globex Group. Der nächste Schritt im Prozess wartet nun auf Sie: "
     "Sie sind zum Online-Assessment eingeladen. Sie können das Verfahren noch bis einschließlich 19.10.2026 abschließen.", "NEEDS_YOU"),   # automated test the user must take: NeedsAttention, not "shortlisted"
    ("BIP Careers <sender@workflow.email.oraclecloud.com>", "Continue to apply for the job AI Engineer",
     "Hello Alex, We saved a draft of your job application for the job AI Engineer. We invite you to complete and submit your job application. "
     "If you don't submit your job application, the data you entered will be stored for 30 days.", "NEEDS_YOU"),
    ("admin@acme.example", "Thank you for your interest in AI Engineer",
     "Hi Alex, Thank you for submitting your application for AI Engineer. We are currently reviewing your profile to assess your fit for this assignment. "
     "If your experience aligns with the project requirements, we will reach out to discuss the next steps.", "CONFIRM"),
    ("hr@myworkday.com", "Deine Bewerbung bei Initech - AI Engineer (f/m/d) - Life Science and Diagnostics (f/m/d)",
     "Hallo Alex , vielen Dank für dein Interesse an Initech. Wir haben deine Bewerbung für die Position AI Engineer (f/m/d) - Life Science and Diagnostics (f/m/d) erhalten "
     "und freuen uns, dass du Teil unseres Bewerbungsprozesses bist. Wir halten dich auf dem Laufenden!", "CONFIRM"),
    ("Sam Recruiter <sam@hooli.example>", "Deine Bewerbung als AI Consultant (m/w/d) / Your application as AI Consultant (m/w/d)",
     "Hallo Alex, wir freuen uns über dein Interesse an einer Tätigkeit bei Hooli und bedanken uns für deine Bewerbung. Bitte hab Verständnis dafür, dass wir für eine "
     "Rückmeldung noch etwas Zeit benötigen, da wir jede Bewerbung sorgfältig prüfen.", "CONFIRM"),
    ("Bewerbermanagement <bewerbung@acme.example>", "Ihre Bewerbung als Consultant Data & Knowledge Engineering (m/w/d)",
     "Sehr geehrter Herr Example, wir bedanken uns sehr für Ihre Bewerbung und dem damit entgegengebrachten Interesse für unser Unternehmen. Bitte haben Sie Verständnis dafür, "
     "dass wir für eine Rückmeldung noch etwas Zeit benötigen.", "CONFIRM"),
    ("people@ACME <noreply@acme.example>", "Your application at",
     "Dear Alex, Thanks a lot for your application and your interest shown in our company. As the careful analysis of the incoming applications needs some time, "
     "we would like to ask for some patience and will come back to you as soon as possible.", "CONFIRM"),
    ("stellenanzeigen.de <bewerbungsservice@stellenanzeigen.de>", "Kopie deiner Bewerbung von Alex Example als AI & Digital Solutions Engineer (m/w/d) in Sankt Ingbert, Referenznummer: SDE-124545",
     "Sehr geehrte Damen und Herren, ich interessiere mich für die ausgeschriebene Stelle.", "CONFIRM"),
    ("Pat from Acme <pat@acme.example>", "Update zu deiner Bewerbung auf unsere offene Stelle",
     "Hallo Alex, danke für deine Bewerbung auf AI Support Engineer (m/w/d) in München. Für diese Stelle können wir aktuell nicht weiterplanen, das liegt oft am Zeitpunkt "
     "oder an sehr spezifischen Anforderungen für diese Position. Schau gern in unserer Jobbörse, ob etwas anderes für dich dabei ist.", "REJECTION"),
    ("Sam Recruiter <sam@acme-hr.example>", "Acme Construction - Zwischenstand Ihrer Bewerbung",
     "Ihre Bewerbung als Applied AI Engineer. Guten Tag Alex Example, wir möchten Ihnen versichern: Wir haben Sie nicht vergessen! Leider verzögert sich der Auswahlprozess weiterhin. "
     "Ihre Unterlagen befinden sich weiterhin im Auswahlverfahren.", "UNCLASSIFIED"),
    # --- automated test steps = NEEDS_YOU (NeedsAttention, same class as the Globex/ELIGO mail), whatever the company or vendor ---
    ("Acme Coaching GmbH <hr@acme.example>", "Acme Coaching - Bitte fülle den Fragebogen aus",
     "Hallo Alex, deine Bewerbung für die Stelle KI-Automatisierungsingenieur (m/w/d) ist erfolgreich eingereicht worden. Bitte fülle den folgenden Fragebogen aus: Fragebogen zum Persönlichkeitstest. "
     "Das Testergebnis führt nicht zur Ablehnung deiner Bewerbung.", "NEEDS_YOU"),
    ("Harver <noreply@harver.com>", "Complete your assessment for Acme GmbH",
     "Hello Alex, thank you for your application to Acme GmbH. You are invited to take the online assessment. Your username is abc. Please complete it by 20 October.", "NEEDS_YOU"),
    ("Acme HR <hr@acme.de>", "Ihre Bewerbung", "Vielen Dank für Ihre Bewerbung. Der nächste Schritt: Sie sind zum Online-Assessment eingeladen. Bitte laden Sie zusätzlich Ihr Arbeitszeugnis hoch.", "NEEDS_YOU"),
    ("Acme HR <hr@acme.de>", "Einladung zum Interview", "Hallo Alex, wir haben deine Bewerbung gelesen und laden dich gern zu einem Kennenlerngespräch per Teams ein. Bitte wähle einen Termin.", "SHORTLISTED"),
    # --- profile-deletion warnings (user: trash them) -- real wording from mails the user had already trashed ---
    ("Umbrella Corp Talent Acquisition <talent@umbrella.example>", "\"Confidential\" Umbrella Corp: Don't let your profile expire",
     "Hi Alex, interested in a career at Umbrella Corp? Then, let's make sure you don't miss out! Due to inactivity, your profile on our careers portal has been flagged for removal. "
     "This is easily corrected: simply log in and update your profile.", "STALE_PROFILE"),
    ("noreply.sf @ Initech <noreply@initech.com>", "Information zur bevorstehenden Löschung Ihres Profils",
     "Sehr geehrter Herr Example, Ihr Kandidatenprofil war längere Zeit inaktiv. Daher werden alle darin enthaltenen personenbezogenen Daten in 14 Tagen automatisch gelöscht werden. "
     "Falls Sie weiterhin an einer Zusammenarbeit mit unserem Unternehmen interessiert sind, melden Sie sich bitte in Ihrem Profil an.", "STALE_PROFILE"),
    ("Initech Talent Acquisition Team <talent@initech.example>", "Initech Recruiting - GDPR Notification",
     "Hi Alex, your application data is over in 30 days time, after which your data will be deleted automatically. We'd love the opportunity to consider you for future job openings; "
     "please log in to keep your profile.", "STALE_PROFILE"),
    # --- NOT stale-profile warnings: static retention statements inside receipts / rejections stay what they are ---
    ("Acme Analytical <jobs@acme.example>", "Acme: Deine Bewerbung bei uns",
     "Hallo Alex, vielen Dank für deine Bewerbung. Wir haben deine Bewerbung erhalten. Bitte beachte, dass wir deine Bewerbung nach 6 Monaten fristgemäß aus dem System löschen.", "CONFIRM"),
    ("Initech HR <hr@initech.example>", "Initech - Eingangsbestätigung deiner Bewerbung",
     "Vielen Dank für deine Bewerbung, wir haben deine Bewerbung erhalten. Um dein Kandidatenprofil zu löschen, kannst du dich auch hier anmelden.", "CONFIRM"),
    ("HR <hr@x.de>", "Ihre Bewerbung", "Leider haben wir uns für einen anderen Bewerber entschieden. Gemäß der gültigen Datenschutzbestimmungen löschen wir Ihre Daten aus unserer Datenbank.", "REJECTION"),
    # LinkedIn "Your update from X" rejections: decision sentence sits after a long preheader
    ("LinkedIn <jobs-noreply@linkedin.com>", "Your application to AI Platform Engineer (m/w/d) at ACME",
     "Your update from ACME This email was intended for Alex Example (AI Engineer | Proficient in Python) Learn why we included this: https://www.linkedin.com/help You are receiving LinkedIn notification emails. "
     "Your application to AI Platform Engineer (m/w/d) at ACME Applied on Oct 20 Thank you for your interest in the AI Platform Engineer (m/w/d) position at ACME in Germany. "
     "Unfortunately, we will not be moving forward with your application, but we appreciate your time and interest in ACME. Regards, ACME", "REJECTION"),
    # --- mails the user still saw in the inbox after a run ---
    ("Cherry Group <reply@mail.onlyfy.jobs>", "Ihre Daten sind noch gespeichert",
     "Guten Tag Alex Example, wir möchten Sie daran erinnern, dass Ihre persönlichen Daten in unserem System immer noch gespeichert sind. Möchten Sie weitere passende Jobangebote von CHERRY für 12 Monate erhalten, nutzen Sie bitte diesen Link.", "STALE_PROFILE"),
    ("noreply@gdpr.acme-gdpr.example <noreply@gdpr.acme-gdpr.example>", "Erinnerung - Einverständniserklärung / Reminder - Request for Consent",
     "Hallo Alex Example, Wir möchten Sie bei Ihrer nächsten Karriereschritten unterstützen und Sie über aktuelle Jobangebote auf dem Laufenden halten. Die Sicherheit Ihrer persönlichen Daten hat höchste Priorität.", "STALE_PROFILE"),
    ("Precis <no-reply@acme.teamtailor.com>", "We would love to keep considering you for our recruitment!",
     "Hi Alex, A while ago, you either applied for a position or connected to one of our recruitment processes. Now we're wondering if we can keep your information. Extend permission", "STALE_PROFILE"),
    ("HOERBIGER Careers <system@successfactors.eu>", "Dein Konto auf der HOERBIGER Karriereseite wurde erstellt",
     "Hallo Alex, Du hast erfolgreich ein Profil auf unserer Karriereseite erstellt! Bitte vervollständige Dein Profil damit wir Dich besser kennenlernen.", "CONFIRM"),
    ("Etteplan <noreply@trustcruit.com>", "Reminder - We have additional question - submit feedback",
     "Hello A few days ago, you received an email from us where we asked for your anonymous feedback on our application process. The feedback concerns the job with the job title: Applied AI Engineer (m/w/d)", "CONFIRM"),
    ('"AI | Wayne Legal" <ai@wayne-legal.example>', "Ihr Gespräch bei Wayne Legal: neue Uhrzeit am 9. November",
     "Lieber Alex Example, bei uns hat sich für Montag, den 9. November, etwas verschoben. Könnten wir unser Gespräch deshalb eine Dreiviertelstunde später führen, von 17:30 bis 18:00 Uhr?", "NEEDS_YOU"),
    ("Pat Recruiter <pat@acme-corp.example>", "Re: Rescheduling your interview with Acme", "Hi Alex, Of course we can reschedule. Please share a few times next week.", "NEEDS_YOU"),
    ("Invitation Sender <DoNotReply@assessment.example.com>", "Vendor - Einladung zum Online Assessment",
     "Guten Tag Alex Example, vielen Dank für Ihre Bewerbung. Bitte nutzen Sie den folgenden Link, um die Online Assessments zu absolvieren.", "NEEDS_YOU"),
    ('"carbon.talent" <notifications@carbon.talent>', "Roles that fit your skills", "New roles go live every week. CDI - Manager AI Engineer - Paris: Apply with Carbon", None),
    ("Stark <opportunities@careeralerts.stark.example>", "Alex: Jobs for you at Stark Talent Community", "New Jobs matching your profile. A job opening matching your profile has just been posted.", None),
    # --- must stay ignored: private mail and marketing ---
    ("Vermieter <x@example.com>", "AW: 2. Mahnung", "Sehr geehrter Herr Example, Ihre Zahlung ist noch offen.", None),
    ("DeepLearning.AI <hello@newsletter.example>", "Want to uplevel your AI engineering skills? Join us in NYC",
     "Join us for AI Dev NYC. Register today. Unsubscribe", None),
    ("Alex Example <alex.example@gmail.com>", "Re: Bewerbung", "Vielen Dank für Ihre Bewerbung, wir haben sie erhalten.", None),
]
bad = 0
for frm, subj, body, want in CASES:
    got, note = triage_one(M(frm, subj), body)
    if got != want:
        bad += 1
        print(f"WANT {want}, GOT {got} | {subj[:60]} | {note[:70]}")
print(f"{len(CASES) - bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
