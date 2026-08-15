# Data

This project runs on the **NASA/IMS Bearing Dataset** (run-to-failure vibration
snapshots from a 4-bearing test rig, 2003-2004). The raw files are too large
to keep in this git repo, so they're excluded via `.gitignore` — grab them
from one of the links below and drop them in here.

## Get the data

- **Original public source (NASA Prognostics Data Repository, via AWS):**
  https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip
- **Mirror (Google Drive):** `<ADD YOUR GOOGLE DRIVE LINK HERE>` (well i didnt add it for now takes too much drive space)

## Folder layout

Unzip the dataset and arrange it like this — one subfolder per test set:

```
data/
├── set1_data/   # Test-to-failure set 1 (8 channels)
├── set2_data/   # Test-to-failure set 2 (4 channels)
└── set3_data/   # Test-to-failure set 3 (4 channels)
```

Each subfolder should contain the raw tab-separated snapshot files exactly
as they come out of the NASA zip (filenames are timestamps, e.g.
`2003.10.22.12.06.24` — the pipeline sorts on these directly, no renaming
needed).

## Point the app/pipeline at this folder

Either set the environment variable once:

```bash
# macOS/Linux
export IMS_DATA_ROOT="$(pwd)/data"
export IMS_OUTPUT_ROOT="$(pwd)/outputs"

# Windows (persists across sessions)
setx IMS_DATA_ROOT "%cd%\data"
setx IMS_OUTPUT_ROOT "%cd%\outputs"
```

...or just type the full path into the "Data Root" field in the dashboard's
**Section 3: Run Analysis** page.

Set 1 has 8 channels (2 bearings x 4 axes); sets 2 and 3 have 4 channels
(one per bearing) — pass the matching `--n-channels` / dashboard channel
count for whichever set you're processing.
