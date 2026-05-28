# CitySpace

CitySpace is a collection of Python scripts for urban street-space analysis. It covers data conversion, road-network preparation, street-view complexity calculation, average-speed analysis, label generation, train/test split preparation, and prediction post-processing.

## Project Structure

```text
.
|-- average_speed_calculation_scripts/      # Average traffic-speed calculation
|-- data_analysis_scripts/                  # Additional exploratory and temporal analysis scripts
|-- data_conversion_cleaning_scripts/       # CSV, Excel and Shapefile conversion/cleaning tools
|-- data_preparation_scripts/               # Road, POI and street-space data preparation
|-- label_train_split_scripts/              # Label generation and train/test split scripts
|-- prediction_postprocessing_scripts/      # Prediction result post-processing
|-- streetscape_complexity_scripts/         # Street-view complexity and diversity metrics
|-- requirements.txt                        # Python dependency list
`-- 说明文档.md                              # Chinese usage notes
```

## Requirements

- Python 3.9 or newer is recommended.
- GIS dependencies are required by `geopandas`, `osmnx`, `shapely`, and `cityseer`.
- Most scripts assume local CSV/Shapefile input paths. Update the input and output paths in each script before running.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

If geospatial packages fail to install with plain `pip`, use a Conda environment:

```bash
conda create -n cityspace python=3.10
conda activate cityspace
conda install -c conda-forge geopandas shapely scipy scikit-learn osmnx cityseer
python -m pip install -r requirements.txt
```

## Typical Workflow

1. Convert and clean raw tabular or spatial data with scripts in `data_conversion_cleaning_scripts/`.
2. Prepare road-network, POI, semantic and street-space data with scripts in `data_preparation_scripts/`.
3. Calculate average speed with `average_speed_calculation_scripts/ave_speed.py`.
4. Calculate street-view complexity/diversity metrics with scripts in `streetscape_complexity_scripts/`.
5. Generate labels and split datasets with scripts in `label_train_split_scripts/`.
6. Run model training or prediction outside this repository as needed.
7. Post-process prediction results with scripts in `prediction_postprocessing_scripts/`.

## Notes

- The repository contains research scripts rather than a single packaged command-line application.
- Some scripts contain hard-coded Windows paths from the original experiment environment. Replace them with paths on your machine before execution.
- Data formats used by the project include CSV, Excel, Shapefile (`.shp`) and GeoPackage (`.gpkg`).
- Keep large raw datasets and generated result files outside Git unless they are small examples needed for documentation.
