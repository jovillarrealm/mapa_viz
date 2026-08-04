import numpy as np
import pandas as pd


def create_sample_excel(filename="SampleSites_Afa_planas.xlsx"):
    """
    Generates a realistic ichthyology sampling sites Excel file for testing,
    where 'X' represents Latitude and 'Y' represents Longitude as specified in the blueprint.
    """
    np.random.seed(42)
    n_points = 24

    sectors = ["Sector Alto", "Sector Medio", "Sector Bajo", "Caño Yahuarcaca"]
    species = [
        "Astroblepus ubidiai",
        "Apistogramma personata",
        "Hypostomus plecostomus",
        "Bryconops alburnoides",
    ]

    # Latitudes around Amazon/Leticia region (-4.21 to -3.95)
    lats = np.random.uniform(-4.22, -3.95, n_points)
    # Longitudes around (-70.25 to -69.85)
    lons = np.random.uniform(-70.25, -69.85, n_points)

    data = {
        "Codigo_Sitio": [f"SITE_{i + 1:03d}" for i in range(n_points)],
        "X": lats,  # Latitude
        "Y": lons,  # Longitude
        "Sector": np.random.choice(sectors, n_points),
        "Especie_Dominante": np.random.choice(species, n_points),
        "Abundancia_Ind": np.random.randint(5, 150, n_points),
        "Temperatura_C": np.round(np.random.uniform(24.5, 29.8, n_points), 1),
        "pH": np.round(np.random.uniform(6.1, 7.4, n_points), 2),
        "Elevacion_m": np.random.randint(60, 220, n_points),
    }

    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Sample dataset '{filename}' generated with {n_points} sites.")
    return filename


if __name__ == "__main__":
    create_sample_excel()
