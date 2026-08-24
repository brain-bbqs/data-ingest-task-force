# Session: Suthana in-lab project

Adding the Suthana lab's in-lab navigation conversion as `labs/suthana/in-lab/`,
the repository's first lab with more than one project, and registering it in the
dispatch registries (incoming `000530`, standardized `000531`).

## Request 1 — Add the project

> Can you please add a new project for the Suthana lab? project title "in-lab"
>
> incoming dataset: https://dandi.emberarchive.org/dandiset/000530
> standardized output: https://dandi.emberarchive.org/dandiset/000531

(Attached: `README.md`, `Suthana_inLab_DataConversion.py`,
`Suthana_MATdata_full.ipynb` from the original conversion work.)

Asked which layout to use, given that naming this project "in-lab" implies
Suthana will have siblings, and the repository so far mapped one lab to exactly
one dispatch entry. The answer was to add an optional `project` field to the
dispatch registry, so code lives at `labs/suthana/in-lab/` and the project is
keyed `suthana/in-lab`.

## Request 2 — Empty incoming dandisets

> (also, the current datasets have no incoming data sessions yet but will soon;
> will the dispatch pass in that case?)
