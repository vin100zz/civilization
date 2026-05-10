MAP_WIDTH = 80
MAP_HEIGHT = 50
TILE_SIZE = 32
NUM_CIVS = 9
TURN_INTERVAL_SECONDS = 2.0

# Year progression: (threshold_year, years_per_turn)
YEAR_INCREMENTS = [
    (-4000, 50),
    (-1000, 25),
    (500, 10),
    (1500, 5),
    (1800, 2),
    (1950, 1),
]
START_YEAR = -4000

# Growth
FOOD_TO_GROW_BASE = 20  # food needed per population point

# Civilizations
CIV_DATA = [
    {
        "name": "Americans",
        "color": "mediumpurple",
        "city_names": [
            "Washington", "New York", "Boston", "Chicago",
            "Denver", "Seattle", "Miami", "Dallas", "Atlanta", "Phoenix",
        ],
    },
    {
        "name": "Romans",
        "color": "yellow",
        "city_names": [
            "Rome", "Carthage", "Capua", "Neapolis",
            "Antium", "Brundisium", "Massilia", "Corinth", "Ravenna", "Mediolanum",
        ],
    },
    {
        "name": "Chinese",
        "color": "magenta",
        "city_names": [
            "Beijing", "Shanghai", "Canton", "Nanjing",
            "Xian", "Chengdu", "Kaifeng", "Hangzhou", "Wuhan", "Tianjin",
        ],
    },
    {
        "name": "Egyptians",
        "color": "cyan",
        "city_names": [
            "Thebes", "Memphis", "Heliopolis", "Alexandria",
            "Byblos", "Amarna", "Luxor", "Aswan", "Tanis", "Bubastis",
        ],
    },
    {
        "name": "Greeks",
        "color": "green",
        "city_names": [
            "Athens", "Sparta", "Corinth", "Rhodes",
            "Argos", "Mycenae", "Olympia", "Delphi", "Ephesus", "Miletus",
        ],
    },
    {
        "name": "Vikings",
        "color": "orange",
        "city_names": [
            "Stavanger", "Hedeby", "Oslo", "Trondheim",
            "Bergen", "Uppsala", "Kaupang", "Birka", "Nidaros", "Sigtuna",
        ],
    },
    {
        "name": "Spanish",
        "color": "grey",
        "city_names": [
            "Madrid", "Barcelona", "Seville", "Valencia",
            "Toledo", "Cordoba", "Granada", "Bilbao", "Malaga", "Saragossa",
        ],
    },
    {
        "name": "Aztec",
        "color": "lime",
        "city_names": [
            "Tenochtitlan", "Texcoco", "Tlacopan", "Xochimilco",
            "Cholula", "Teotihuacan", "Tula", "Cuernavaca", "Cempoala", "Tlatelolco",
        ],
    },
    {
        "name": "Russia",
        "color": "white",
        "city_names": [
            "Moscow", "Saint Petersburg", "Novgorod", "Kiev",
            "Smolensk", "Yaroslavl", "Rostov", "Kazan", "Vladivostok", "Sochi",
        ],
    },
]
