#!/usr/bin/env python3
"""Regression tests for rejection_classifier. Run: python test_classifier.py  (exit 1 on failure).
Add a case whenever the classifier misjudges a real email (anonymise it to the deciding sentences)."""
import os; os.environ.setdefault("JOBTRACKER_USER_HINTS", "alex.example")  # the tester's own address
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rejection_classifier import classify  # noqa: E402

REJECT = [
    "Nach sorgfältiger Prüfung müssen wir Dir leider mitteilen, dass wir Deine Bewerbung nicht weiter berücksichtigen können.",
    "Leider hat es diesmal nicht geklappt – dein Profil passt nicht ganz zu den Anforderungen dieser Rolle.",
    "Auch wenn uns deine Bewerbungsunterlagen sehr gut gefallen haben, können wir diese zum heutigen Zeitpunkt leider nicht berücksichtigen.",
    "Wir haben uns leider für einen anderen Bewerber entschieden.",
    "Zum jetzigen Zeitpunkt können wir Ihnen jedoch keine passende Position anbieten.",
    "Die Stelle ist aktuell leider schon vergeben.",
    "Unfortunately, we have decided to move forward with other candidates.",
    "We regret to inform you that we will not be moving forward with your application.",
    "Unfortunately we could not shortlist your application.",
    "Looking at the roles we have open, we don't see a strong match for your background.",
    "Helaas moeten we je informeren dat we hebben besloten verder te gaan met andere kandidaten.",
    "Just to let you know the vacancy has now been closed.",
    "Dear Alex, we decided to pursue other candidates at this time.",
    "Unfortunately, we can't consider you for the position because your German proficiency is below C1.",
    "While we won't be progressing with your application for this particular opportunity, we want to acknowledge your potential.",
    "Für diese Stelle können wir aktuell nicht weiterplanen, das liegt oft am Zeitpunkt oder an sehr spezifischen Anforderungen für diese Position.",
    "Nach sorgfältiger Abwägung müssen wir ehrlich sein: Die Vorstellungen bzgl. der für diese Rolle erforderlichen Deutschkenntnisse (C1-2) passen aktuell nicht gut genug zusammen, um den Prozess gemeinsam weiterzuführen.",   # Epikur 2026-11-18
]
NOT_REJECT = [
    "Leider verzögert sich der Auswahlprozess weiterhin. Dafür möchten wir uns entschuldigen.",
    "Uns fehlt nur noch dein Ergebnis aus dem Persönlichkeitstest. Ohne diesen Schritt können wir deine Bewerbung leider nicht weiter bearbeiten.",
    "Due to an internal scheduling change, we unfortunately need to reschedule your interview.",
    "Unfortunately, due to the high volume of interest we aren't able to personally respond to every candidate.",
    "Wir haben Ihre Bewerbung erhalten und melden uns. Falls wir Ihre Bewerbung nicht berücksichtigen können, informieren wir Sie.",
    "If you are not selected for this specific position, keep an eye on our jobs page.",
    "Otherwise, we will delete your data and will not be able to continue working with you.",
    "Whether this role is the right fit for your background, you can see in your match score.",
    "Der 28.07. passt uns leider nicht, wie wäre es mit dem 29.07. um 10 Uhr?",
    "Thank you for your application. We will review it and be in touch if your qualifications match the requirements of the role.",
    "We are delighted to invite you to a first interview and would like to move forward with your application.",
    "Sobald wir eine engere Auswahl getroffen haben, werden wir uns umgehend mit Dir in Verbindung setzen.",
    "Der Arbeitgeber hat diese Stelle möglicherweise schon besetzt oder die Stelle ist nicht mehr verfügbar.",
]
# --- adversarial: look like rejections but are NOT (a false positive here would hide a real email) -------
NOT_REJECT += [
    "We regret to inform you that your interview on Monday has to be rescheduled.",
    "Leider müssen wir den Termin am Montag absagen und schlagen Dienstag um 10 Uhr vor.",
    "Die Absage des Termins tut uns leid, wir melden uns mit einem neuen Vorschlag.",
    "The role you viewed has been filled. Here are 5 similar jobs you might like.",
    "As requested, we have cancelled your application and deleted your data.",
    "Do you know other candidates for this position? Refer them and receive a bonus.",
    "Unfortunately we are unable to offer the requested salary, but we can offer 70.000 EUR plus bonus.",
    "Unfortunately, we are not able to offer you a parking space on site, but remote work is possible.",
    "We have decided to move forward with your application and invite you to a first interview.",
    "We regret that we missed your call yesterday; when can we speak?",
    "Leider können wir das Vorstellungsgespräch nicht vor Ort durchführen, es findet per Teams statt.",
    "Wir bedauern, dass die Bewerbungsfrist am Freitag endet - bewirb dich bis dahin.",
    "Unfortunately your CV upload failed. Please try again.",
    "Leider haben wir noch keine Rückmeldung vom Fachbereich, wir melden uns nächste Woche.",
    "Thanks for your interest in working as an AI Systems Engineer. I am thrilled to invite you for your first video interview with us.",
    "Sie sind zum Online-Assessment eingeladen. Sie können das Verfahren noch bis einschließlich 19.10.2026 abschließen.",
    "Leider verzögert sich der Auswahlprozess weiterhin. Ihre Unterlagen befinden sich weiterhin im Auswahlverfahren und werden sorgfältig geprüft.",
]
bad = 0
for t in REJECT:
    r = classify("hr@example.com", "Deine Bewerbung", "Hallo Alex, vielen Dank für deine Bewerbung. " + t + " Alles Gute.")
    if r["verdict"] != "REJECTION":
        bad += 1; print("SHOULD REJECT :", r["verdict"], "|", t[:90])
for t in NOT_REJECT:
    r = classify("hr@example.com", "Deine Bewerbung", "Hallo Alex, vielen Dank für deine Bewerbung. " + t + " Viele Grüße")
    if r["verdict"] == "REJECTION":
        bad += 1; print("SHOULD NOT    :", r["verdict"], "|", t[:90], "|", r["why"])
mixed = classify("hr@example.com", "Deine Bewerbung", "Vielen Dank für deine Bewerbung. Leider müssen wir dir mitteilen, dass wir deine Bewerbung für Stelle A nicht berücksichtigen können. Für die Stelle B laden wir dich gern zu einem Kennenlerngespräch ein.")
bad += mixed["verdict"] == "REJECTION"
alert = classify("alerts@jobs.com", "Job alert", "New jobs for you. The position Data Engineer has been filled, see more openings.")
bad += alert["verdict"] == "REJECTION"
r = classify("Alex Example <alex.example@gmail.com>", "Re: x", "Leider haben wir uns für einen anderen Bewerber entschieden.")
bad += r["verdict"] == "REJECTION"
r = classify("hr@example.com", "Re: Bewerbung", "Danke.\n> Leider haben wir uns für einen anderen Bewerber entschieden.")
bad += r["verdict"] == "REJECTION"
total = len(REJECT) + len(NOT_REJECT) + 4
print(f"{total - bad}/{total} passed")
sys.exit(1 if bad else 0)
