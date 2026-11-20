#!/usr/bin/env python3
"""Regression tests for confirmation_classifier. Run: python test_confirmation.py (exit 1 on failure).
Every NOT case below is a REAL mail that once looked like a receipt but was a rejection / invitation / request
(anonymised to the deciding sentences). A false positive here would hide a real email."""
import os; os.environ.setdefault("JOBTRACKER_USER_HINTS", "alex.example")  # the tester's own address
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from confirmation_classifier import classify_confirmation  # noqa: E402

OK = [
    ("Lieber Alex, wir bedanken uns für Deine Bewerbung. Eingang der Online-Bewerbung als AI Engineer. Wir melden uns.", ""),
    ("Wir freuen uns sehr über Deine Bewerbung bei BuildlinX. Du wirst in Kürze von uns hören.", ""),
    ("We appreciate your interest in our Organisation and acknowledge receipt of your application for the position of Junior Systems Engineer.", ""),
    ("Dear Alex, Thank you for applying to the Machine Learning Engineer position. We have received your application and will be in touch within 14 days.", ""),
    ("Hallo Alex, vielen Dank für deine Bewerbung. Wir haben deine Bewerbung erhalten und melden uns bei dir.", ""),
    # --- receipts that used to be invisible to the triage (2026-10-08) ---
    ("Hallo Alex, wir freuen uns über dein Interesse an einer Tätigkeit bei Hooli und bedanken uns für deine Bewerbung. Bitte hab Verständnis dafür, dass wir für eine Rückmeldung noch etwas Zeit benötigen.", ""),
    ("Sehr geehrter Herr Example, wir bedanken uns sehr für Ihre Bewerbung und dem damit entgegengebrachten Interesse für unser Unternehmen. Bitte haben Sie Verständnis dafür, dass wir für eine Rückmeldung noch etwas Zeit benötigen.", ""),
    ("Dear Alex, Thanks a lot for your application and your interest shown in our company. As the careful analysis needs some time, we would like to ask for some patience.", ""),
    ("Hi Alex, Thank you for submitting your application for AI Engineer. We are currently reviewing your profile to assess your fit for this assignment.", ""),
    ("Hallo Alex , vielen Dank für dein Interesse an Initech. Wir haben deine Bewerbung für die Position AI Engineer (f/m/d) - Life Science and Diagnostics (f/m/d) erhalten und freuen uns, dass du Teil unseres Bewerbungsprozesses bist.", ""),
    ("Guten Tag Alex Example, wir freuen uns über Ihr Interesse an einer Tätigkeit bei uns und bedanken uns für Ihre Bewerbung. Wir setzen uns so bald wie möglich mit Ihnen in Verbindung.", ""),
    ("Hallo Alex, wir freuen uns über dein Interesse an einer Tätigkeit bei uns und bedanken uns für deine Bewerbung. Wir bitten um Verständnis, dass es derzeit zu einer längeren Bearbeitungszeit kommt.", ""),
]
# Known CONSERVATIVE misses (deliberate: precision over recall). These stay UNCLEAR and the user/Claude reads them:
#   signature with "Telefon", "wir benötigen noch etwas Zeit", "jedoch", long texts -> never auto-filed.
NOT = [
    "Thank you for applying. While we are unable to offer you this position at this time, we hope to stay connected.",
    "Vielen Dank für deine Bewerbung. Für unsere Kundenprojekte benötigen wir jedoch ein höheres Sprachniveau, als du angegeben hast.",
    "Thank you for applying. Since working at our company requires a proficient level of Dutch, we are not able to pursue your application.",
    "Vielen Dank für Ihre Bewerbung. Möchten wir Sie zu einem ersten Gespräch am Donnerstag um 15:00 Uhr einladen. Bitte geben Sie uns Bescheid.",
    "Vielen Dank für Ihre Bewerbung. Aufgrund der Vielzahl ist es uns nur möglich die Bewerber in die engere Wahl zu berücksichtigen, die dem Profil entsprechen.",
    "Thank you for applying. Unfortunately we have decided to move forward with other candidates.",
    "Your application was received. To move forward with your application, we kindly ask you to provide a certificate.",
    "Danke für deine Bewerbung. Bitte bestätige einmal, dass diese E-Mail dich erreicht hat.",
    "Thank you for your application. As a next step please complete the online assessment within 7 days.",
    "We received your application. While we won't be progressing with your application for this opportunity, we wish you the best.",
    "Thank you for your application! Please send us your salary expectation and earliest start date.",
    "Wir haben Ihre Bewerbung erhalten. Leider wurde die Stelle inzwischen besetzt.",
    # "benötigen" next to skills/language is a rejection signal; next to "Zeit" it is only a receipt (see OK above)
    "Vielen Dank für Ihre Bewerbung. Für diese Position benötigen wir verhandlungssichere Deutschkenntnisse, die Ihre Unterlagen nicht belegen.",
    "Danke für deine Bewerbung. Du bist zum Online-Assessment eingeladen. Dein Benutzername lautet: abc123.",
    "Thanks for your interest in working as an AI Systems Engineer. I am thrilled to invite you for your first video interview.",
    "Hello Alex, we saved a draft of your job application. We invite you to complete and submit your job application.",
]
bad = 0
for t, _ in OK:
    r = classify_confirmation("hr@example.com", "Ihre Bewerbung", t)
    if r["verdict"] != "CONFIRMATION":
        bad += 1; print("SHOULD CONFIRM  :", r["verdict"], "|", r["why"][:50], "|", t[:70])
for t in NOT:
    r = classify_confirmation("hr@example.com", "Ihre Bewerbung", t)
    if r["verdict"] == "CONFIRMATION":
        bad += 1; print("SHOULD NOT      :", t[:90])
e = classify_confirmation("LinkedIn <jobs-noreply@linkedin.com>", "Alex, your application was sent to Acme GmbH", "Your application was sent to Acme GmbH. Application from Alex Example.")
bad += not (e["verdict"] == "CONFIRMATION" and e["easyapply"])
u = classify_confirmation("Alex Example <alex.example@gmail.com>", "Re: Bewerbung", "Vielen Dank für Ihre Bewerbung, wir haben sie erhalten.")
bad += u["verdict"] == "CONFIRMATION"
total = len(OK) + len(NOT) + 2  # +2: easy-apply, user-sent
print(f"{total - bad}/{total} passed")
sys.exit(1 if bad else 0)
