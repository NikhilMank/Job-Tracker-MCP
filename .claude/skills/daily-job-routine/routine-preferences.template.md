# Daily routine preferences

<!-- Private. Lives in data/routine-preferences.md (git-ignored). Created by the daily-job-routine skill on the
     first run from your answers. Edit freely, or say "change my routine preferences". Anything not set here is left alone. -->

## Setup
- preferences_version: 1          <!-- format version of this file; managed by the update tooling, do not edit -->
- gmail_enabled: (not set)         <!-- use the Gmail features at all: yes | no -->
- label_prefix: (not set)          <!-- parent Gmail label, e.g. JobApplications; skills substitute it for the default name in their text -->

## Mail handling
<!-- "trash" always means Gmail's Trash (an undo log is written, mail stays recoverable ~30 days). Nothing is deleted permanently. -->

- job_alerts: (not set)            <!-- job-board suggestions/alerts (LinkedIn, Indeed, StepStone, Glassdoor, XING ...): leave | trash -->
- job_alerts_report_roles: (not set) <!-- only if job_alerts is trash: list roles seen in the alerts before trashing? yes | no -->
- company_job_letters: (not set)   <!-- job-agent letters from employers' career sites: leave | ask-each-run | trash-all | trash-unless-matching-role (your own role keywords live in data/role_keywords.json) -->
- stale_profile_mails: (not set)   <!-- "your profile will be deleted / keep my data?" mails: leave | trash -->
- low_value_notices: (not set)     <!-- "your application was viewed", "selection is delayed" mails: leave | trash -->

## Filing and labels
<!-- Every Gmail label belongs to one feature. A label is created ONLY if you say yes to its feature. -->
- file_receipts: (not set)         <!-- move application confirmations out of the inbox into the parent label: yes | no -->
- label_easyapply: (not set)       <!-- also tag LinkedIn Easy Apply receipts with a sub-label (needs file_receipts): yes | no -->
- file_rejections: (not set)       <!-- move rejections out of the inbox into the Rejected label: yes | no -->
- label_shortlisted: (not set)     <!-- star + label positive replies (interview invitations); they stay in the inbox: yes | no -->
- label_needs_attention: (not set) <!-- label mail that asks you to do something (assessments, bookings); stays in the inbox: yes | no -->
- label_attended: (not set)        <!-- a label you add yourself to threads you handled, so the routine stops reminding you (needs label_needs_attention): yes | no -->
- label_accepted: (not set)        <!-- a label for offers/contracts, used when syncing the tracker from Gmail: yes | no -->
- mark_rejected_in_tracker: (not set) <!-- set the matching job to "rejected" in the tracker: yes | ask -->

## Notes
<!-- Anything else the routine should respect, in your own words. -->
