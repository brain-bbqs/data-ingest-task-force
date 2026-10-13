# Session: BEP047 conversion setup for the Chang lab

This session sets up the Chang lab conversion from incoming Dandiset 000517 to
standardized Dandiset 000556, beginning with source-data intake and a BEP047
source-to-output mapping for review before any conversion code is written.

## Request 1 — Set up the Chang lab conversion

> Please set up a new conversion for the Chang lab, working through the
> new-conversion skills in .agents/skills/ in order: lab-intake, then
> lab-conversion-plan, then stop for my review of the plan before running
> lab-scaffold and lab-register. Finish with lab-lessons, encoding anything
> this conversion taught back into the skills.
>
> - Lab / PI: Chang, Yale University 
> - Grant award number: U01DA063534
> - Project name: Toward comprehensive models of naturalistic cooperation and competition in primates
> - Incoming dandiset: https://dandi.emberarchive.org/dandiset/000517
> - Standardized output dandiset: https://dandi.emberarchive.org/dandiset/000556
> - Data standard: BIDS (BEP047) for video (.avi) files and map the json file contents to a common events.tsv and json sidecar
> - Metadata: See the folder Code/data-ingest-task-force/temp_data/chang/000517 for the unstandardized dataset. There are data for 3 sessions with each session consisting of 2 subjects (dyadic interactions). Each session should have video (.avi) files that are paired with event and other session metadata information (.json) files.
> - Expected output example: Please see the BEP047 examples on this PR to help format the output: https://github.com/bids-standard/bids-examples/pull/523/changes.
