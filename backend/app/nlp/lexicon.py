"""French vocabulary linking words of a question to ontology resources.

Class and property names come from the OWL file (CamelCase split into words),
completed with hand-written French synonyms. Every phrase is normalised the
same way as the question (spaCy lemma -> NLTK Snowball stem -> no accents),
so plurals and conjugated verbs match ("centrales" = "centrale",
"alimentent" = "alimente").
"""
import re

# ------------------------------------------------------------------ classes
CLASS_SYNONYMS: dict[str, list[str]] = {
    "SourceProduction": ["source", "source d'énergie", "source de production", "centrale", "centrale électrique",
                         "producteur", "installation de production"],
    "Solaire": ["solaire", "centrale solaire", "ferme solaire", "énergie solaire", "panneau solaire"],
    "Photovoltaique": ["photovoltaïque", "centrale photovoltaïque", "panneau photovoltaïque"],
    "Thermodynamique": ["solaire thermodynamique", "thermodynamique"],
    "Eolien": ["éolien", "éolienne", "parc éolien", "centrale éolienne", "ferme éolienne", "énergie éolienne"],
    "EolienTerrestre": ["éolien terrestre", "éolienne terrestre"],
    "EolienOffshore": ["éolien offshore", "éolienne offshore", "éolien en mer", "offshore"],
    "Hydraulique": ["hydraulique", "hydroélectrique", "centrale hydraulique", "centrale hydroélectrique"],
    "BarrageHydraulique": ["barrage", "barrage hydraulique"],
    "MicroCentrale": ["microcentrale", "micro centrale"],
    "Biomasse": ["biomasse", "centrale biomasse", "centrale à biomasse"],
    "Biogaz": ["biogaz"],
    "Geothermique": ["géothermique", "géothermie", "centrale géothermique"],
    "Stockage": ["stockage", "système de stockage", "unité de stockage", "stockeur"],
    "Batterie": ["batterie", "accumulateur"],
    "BatterieLithium": ["batterie lithium", "batterie au lithium", "lithium"],
    "BatterieAcidePlomb": ["batterie plomb", "batterie au plomb"],
    "StockageHydraulique": ["stockage hydraulique"],
    "StationPompage": ["station de pompage", "pompage"],
    "Hydrogene": ["hydrogène", "stockage hydrogène", "station hydrogène"],
    "Electrolyseur": ["électrolyseur"],
    "PileACombustible": ["pile à combustible"],
    "Supercondensateur": ["supercondensateur"],
    "VolantInertie": ["volant d'inertie", "volant"],
    "Batiment": ["bâtiment", "édifice"],
    "Residentiel": ["résidentiel", "logement"],
    "Maison": ["maison"],
    "Immeuble": ["immeuble", "résidence"],
    "Industriel": ["industriel"],
    "Usine": ["usine"],
    "Entrepot": ["entrepôt"],
    "Commercial": ["commercial", "commerce"],
    "CentreCommercial": ["centre commercial"],
    "Boutique": ["boutique", "magasin"],
    "Hospitalier": ["hospitalier"],
    "Hopital": ["hôpital", "hôpitaux"],
    "Clinique": ["clinique"],
    "Educatif": ["éducatif", "établissement scolaire", "établissement d'enseignement"],
    "Ecole": ["école"],
    "Universite": ["université", "faculté", "fac", "campus"],
    "LigneTransport": ["ligne", "ligne de transport", "ligne électrique", "câble", "réseau"],
    "HauteTension": ["haute tension", "ligne haute tension", "ligne ht"],
    "MoyenneTension": ["moyenne tension", "ligne moyenne tension"],
    "BasseTension": ["basse tension", "ligne basse tension"],
    "MobiliteElectrique": ["mobilité électrique"],
    "VehiculeElectrique": ["véhicule", "véhicule électrique"],
    "VoitureElectrique": ["voiture", "voiture électrique"],
    "BusElectrique": ["bus", "bus électrique"],
    "BorneRecharge": ["borne", "borne de recharge"],
    "CapteurIoT": ["capteur", "capteur iot"],
    "CompteurIntelligent": ["compteur", "compteur intelligent"],
    "PlateformeGestion": ["plateforme", "plateforme de gestion"],
    "ModelePrediction": ["modèle de prédiction", "modèle de prévision", "modèle"],
    "SystemeIntelligent": ["système intelligent"],
}

# --------------------------------------------------------- data properties
# A synonym can map to several properties; the one whose rdfs:domain matches
# the class being asked about is chosen at query time.
DATA_PROPERTY_SYNONYMS: dict[str, list[str]] = {
    "puissance": ["puissance", "puissant", "puissante", "produire", "produit"],
    "productionAnnuelle": ["production annuelle", "production", "production par an"],
    "rendement": ["rendement", "efficacité"],
    "emissionCO2": ["émission", "émission de co2", "co2", "émettre", "pollution"],
    "anneeMiseService": ["année de mise en service", "mise en service", "mis en service"],
    "capacite": ["capacité", "capacité de stockage"],
    "tauxCharge": ["charge", "taux de charge", "niveau de charge", "chargé"],
    "dureeVieAnnees": ["durée de vie"],
    "tempsRechargeHeures": ["temps de recharge"],
    "surface": ["surface", "superficie"],
    "nbOccupants": ["occupant", "habitant", "nombre d'occupants"],
    "consommation": ["consommation", "consommer", "énergivore"],
    "adresse": ["adresse", "localisation", "situé"],
    "anneeConstruction": ["année de construction", "construit"],
    "classeEnergetique": ["classe énergétique", "étiquette énergétique"],
    "tension": ["tension", "voltage"],
    "longueur": ["longueur", "long"],
    "capaciteTransport": ["capacité de transport"],
    "pertes": ["perte", "pertes"],
    "anneePose": ["année de pose", "posé"],
}

# Same French word, other domain: (synonym owner -> alternatives)
PROPERTY_ALTERNATIVES: dict[str, list[str]] = {
    "puissance": ["puissance", "puissanceStockage", "puissanceCharge"],
    "rendement": ["rendement", "rendementStockage"],
    "capacite": ["capacite", "capaciteTransport", "capaciteVehicule"],
}

# -------------------------------------------------------- object properties
RELATION_SYNONYMS: dict[str, list[str]] = {
    "alimente": ["alimenter", "alimente", "alimentation", "fournir", "fournit", "approvisionner", "desservir"],
    "stocke": ["stocker", "stocke", "stockée"],
    "injecteDans": ["injecter", "injecte", "injection"],
    "estConnecteA": ["connecter", "connectée", "relier", "reliée", "raccordée entre"],
    "recharge": ["recharger", "recharge"],
    "estRaccordeeA": ["raccorder", "raccordée"],
    "mesure": ["mesurer", "mesure"],
    "surveille": ["surveiller", "surveille"],
    "predit": ["prédire", "prédit", "prévoir"],
    "gere": ["gérer", "gère", "gestion"],
    "estPlusPuissantQue": ["plus puissant que"],
}

# ---------------------------------------------------------------- values
UNITS: dict[str, tuple[str, float]] = {
    # unit -> (canonical unit, multiplier)
    "kw": ("kW", 1), "mw": ("kW", 1000), "gw": ("kW", 1_000_000),
    "kwh": ("kWh", 1), "mwh": ("kWh", 1000), "gwh": ("kWh", 1_000_000),
    "%": ("%", 1), "pourcent": ("%", 1), "pourcents": ("%", 1),
    "km": ("km", 1), "kilomètre": ("km", 1), "kilomètres": ("km", 1),
    "kv": ("kV", 1), "m2": ("m²", 1), "m²": ("m²", 1), "ans": ("ans", 1), "an": ("ans", 1),
}

# Which property a unit points to, per base class (used when no property word is present)
UNIT_PROPERTY: dict[str, dict[str, str]] = {
    "kW": {"SourceProduction": "puissance", "Stockage": "puissanceStockage", "LigneTransport": "capaciteTransport",
           "MobiliteElectrique": "puissanceCharge"},
    "kWh": {"Batiment": "consommation", "Stockage": "capacite", "SourceProduction": "productionAnnuelle",
            "MobiliteElectrique": "capaciteVehicule"},
    "%": {"Stockage": "tauxCharge", "SourceProduction": "rendement", "LigneTransport": "pertes"},
    "km": {"LigneTransport": "longueur"},
    "kV": {"LigneTransport": "tension"},
    "m²": {"Batiment": "surface"},
}

# Default measure of each family (aggregations / superlatives without a property word)
DEFAULT_PROPERTY: dict[str, str] = {
    "SourceProduction": "puissance",
    "Stockage": "capacite",
    "Batiment": "consommation",
    "LigneTransport": "capaciteTransport",
    "MobiliteElectrique": "capaciteVehicule",
}

UNIT_OF_PROPERTY: dict[str, str] = {
    "puissance": "kW", "puissanceStockage": "kW", "capaciteTransport": "kW", "puissanceCharge": "kW",
    "consommation": "kWh", "capacite": "kWh", "capaciteVehicule": "kWh",
    "tauxCharge": "%", "rendement": "%", "rendementStockage": "%", "pertes": "%",
    "longueur": "km", "tension": "kV", "surface": "m²",
}

# Comparators, matched on the accent-free lowercase question (order matters: longest first)
COMPARATORS: list[tuple[str, str]] = [
    (r"superieure? ou egale? a|au moins|minimum de|>=|≥", ">="),
    (r"inferieure? ou egale? a|au plus|au maximum|maximum de|<=|≤", "<="),
    (r"plus de|plus que|superieure?s? a|au[- ]dessus de|depass\w*|excede\w*|>", ">"),
    (r"moins de|moins que|inferieure?s? a|en[- ]dessous de|sous les|<", "<"),
    (r"egale? a|exactement|=", "="),
]

AGGREGATES: list[tuple[str, str]] = [
    (r"\b(total|totale|somme|cumul\w*|au total)\b", "SUM"),
    (r"\b(moyenne|moyen)\b(?! etat)", "AVG"),
    (r"\b(maximum|maximale?|max)\b", "MAX"),
    (r"\b(minimum|minimale?|min)\b", "MIN"),
]

SUPERLATIVE = re.compile(r"\b(?:le|la|les|l')\s*(plus|moins)\s+(\w+)")

# Status words -> (property, value). Lines use sg:etatLigne, sources sg:actif.
STATUS_PATTERNS: list[tuple[str, str, object]] = [
    (r"bon etat|en bon etat", "etatLigne", "Bon"),
    (r"mauvais etat", "etatLigne", "Mauvais"),
    (r"etat moyen|moyen etat", "etatLigne", "Moyen"),
    (r"hors service|en panne|a l'arret|\barretee?s?\b|\binacti(?:f|fs|ve|ves)\b", "actif", False),
    (r"\bacti(?:f|fs|ve|ves)\b|en service|en marche|en fonctionnement|operationnel\w*", "actif", True),
    (r"\bindisponibles?\b", "disponible", False),
    (r"\bdisponibles?\b", "disponible", True),
]


def split_camel(name: str) -> str:
    """'EolienTerrestre' -> 'eolien terrestre'"""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").lower()
