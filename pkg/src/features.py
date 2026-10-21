"""Définition des variables : cible, features du modèle PD et variables d'imputation."""

LOAN_ID = "loan_id"
TARGET = "loan_status"
TARGET_MAPPING = {"Fully Paid": 0, "Charged Off": 1}

TERM_VALUES = [" 36 months", " 60 months"]
TERM_MONTHS = {" 36 months": 36, " 60 months": 60}
GRADES = ["A", "B", "C", "D", "E", "F", "G"]
EMP_LENGTHS = [
    "< 1 year", "1 year", "2 years", "3 years", "4 years", "5 years",
    "6 years", "7 years", "8 years", "9 years", "10+ years",
]
HOME_OWNERSHIPS = ["OWN", "MORTGAGE", "RENT", "ANY", "OTHER", "NONE"]

# --- Features du modèle PD ---
NUM_FEATURES = [
    "int_rate", "installment", "annual_inc", "dti", "tot_cur_bal", "open_acc_6m",
    "total_bal_il", "inq_fi", "mort_acc", "num_sats",
]
CAT_FEATURES = ["term", "grade", "emp_length", "home_ownership"]
# Ordre des modalités pour l'OrdinalEncoder, aligné sur CAT_FEATURES
CAT_ORDER = [TERM_VALUES, GRADES, EMP_LENGTHS, HOME_OWNERSHIPS]
MODEL_FEATURES = NUM_FEATURES + CAT_FEATURES

# Montants observés après l'octroi : jamais utilisés comme features (fuite de données)
OUTCOME_AMOUNTS = ["out_prncp", "total_pymnt", "recoveries"]

# Colonnes attendues dans le fichier source (en plus de LOAN_ID)
SOURCE_COLUMNS = MODEL_FEATURES + [TARGET] + OUTCOME_AMOUNTS

# --- Imputation ---
# Variables candidates à l'imputation déterministe (moyenne/mode)
DET_IMPUTE_VARS = MODEL_FEATURES + [TARGET]
# Variables imputées par k-NN hot-deck, et variables auxiliaires servant à trouver les voisins
KNN_TARGET_VARS = ["open_acc_6m", "total_bal_il", "inq_fi"]
KNN_AUX_NUM = ["dti", "tot_cur_bal", "int_rate", "annual_inc", "mort_acc"]
KNN_AUX_ORD = ["grade"]
KNN_AUX_NOM = ["home_ownership"]
