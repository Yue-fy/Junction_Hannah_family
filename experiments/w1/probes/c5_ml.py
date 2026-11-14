"""c5 multilingual operator probe (W1-written 04:40, hand-translated BEFORE any run; not from any split).

18 operator questions (c5_en.txt) x 6 languages nobody tuned the ifc parser on (pl, et, es, cs, hu, sv).
Gold = the English reference answers (checked by hand against the model at 04:38, see c5_en.txt run).
Rows: (lang, idx, question). GOLD[idx] = (value, kind) with kind num|text|lowconf."""
D = "data/ifc_models/"
DUP = D + "bsc-duplex_duplex-a-20110907.ifc"
FZK = D + "kit-fzk-haus_ac20-fzk-haus.ifc"
PATHS = [DUP] * 14 + [FZK] * 4
GOLD = [(6, "num"), (24, "num"), (114.254, "num"), (12.634, "num"), ("Level 2", "text"), (14, "num"),
        (57.143, "num"), (6, "num"), (105.358, "num"), (345.663, "num"), (2700, "num"), (22.043, "num"),
        (0, "lowconf"), (125.33, "num"), (9, "num"), (74.509, "num"), (1.3265, "num"), (7, "num")]
Q = {
"en": """How many doors are on 'Level 1'?
How many windows does the whole model have?
What is the total net floor area of all rooms on 'Level 2'?
What is the average room area on 'Level 1'?
Which storey has more doors, 'Level 1' or 'Level 2'?
How many more windows does 'Level 2' have than 'Level 1'?
What percentage of all doors are on 'Level 2'?
How many rooms on 'Level 1' are larger than 10 m²?
What is the total length of the walls on 'Level 1' in metres?
What is the total wall length on 'Level 1' in feet?
If each door costs 450 euros, what do all doors on 'Level 1' cost?
What is the area of the largest room on 'Level 2'?
How many columns are on 'Level 1'?
What is the total volume of the slabs in the model?
How many windows are on 'Erdgeschoss'?
What is the total room area of 'Dachgeschoss'?
How many times larger is the room area of 'Erdgeschoss' than that of 'Dachgeschoss'?
How many rooms are there on 'Erdgeschoss' and 'Dachgeschoss' together?""",
"pl": """Ile drzwi jest na 'Level 1'?
Ile okien ma cały model?
Jaka jest łączna powierzchnia netto wszystkich pomieszczeń na 'Level 2'?
Jaka jest średnia powierzchnia pomieszczenia na 'Level 1'?
Która kondygnacja ma więcej drzwi, 'Level 1' czy 'Level 2'?
O ile więcej okien ma 'Level 2' niż 'Level 1'?
Jaki procent wszystkich drzwi znajduje się na 'Level 2'?
Ile pomieszczeń na 'Level 1' ma powierzchnię większą niż 10 m²?
Jaka jest całkowita długość ścian na 'Level 1' w metrach?
Jaka jest całkowita długość ścian na 'Level 1' w stopach?
Jeśli każde drzwi kosztują 450 euro, ile kosztują wszystkie drzwi na 'Level 1'?
Jaka jest powierzchnia największego pomieszczenia na 'Level 2'?
Ile słupów jest na 'Level 1'?
Jaka jest całkowita objętość stropów w modelu?
Ile okien jest na 'Erdgeschoss'?
Jaka jest łączna powierzchnia pomieszczeń na 'Dachgeschoss'?
Ile razy większa jest powierzchnia pomieszczeń 'Erdgeschoss' niż 'Dachgeschoss'?
Ile pomieszczeń jest łącznie na 'Erdgeschoss' i 'Dachgeschoss'?""",
"et": """Mitu ust on korrusel 'Level 1'?
Mitu akent on kogu mudelis?
Kui suur on kõigi ruumide netopõrandapind kokku korrusel 'Level 2'?
Milline on ruumi keskmine pindala korrusel 'Level 1'?
Kummal korrusel on rohkem uksi, 'Level 1' või 'Level 2'?
Mitu akent rohkem on korrusel 'Level 2' kui korrusel 'Level 1'?
Mitu protsenti kõigist ustest asub korrusel 'Level 2'?
Mitu ruumi korrusel 'Level 1' on suuremad kui 10 m²?
Kui pikk on seinte kogupikkus korrusel 'Level 1' meetrites?
Kui pikk on seinte kogupikkus korrusel 'Level 1' jalgades?
Kui iga uks maksab 450 eurot, kui palju maksavad kõik uksed korrusel 'Level 1'?
Kui suur on suurima ruumi pindala korrusel 'Level 2'?
Mitu sammast on korrusel 'Level 1'?
Kui suur on mudelis olevate plaatide kogumaht?
Mitu akent on korrusel 'Erdgeschoss'?
Kui suur on ruumide kogupindala korrusel 'Dachgeschoss'?
Mitu korda suurem on korruse 'Erdgeschoss' ruumide pindala kui korruse 'Dachgeschoss' oma?
Mitu ruumi on korrustel 'Erdgeschoss' ja 'Dachgeschoss' kokku?""",
"es": """¿Cuántas puertas hay en 'Level 1'?
¿Cuántas ventanas tiene todo el modelo?
¿Cuál es la superficie neta total de todas las habitaciones en 'Level 2'?
¿Cuál es la superficie media de las habitaciones en 'Level 1'?
¿Qué planta tiene más puertas, 'Level 1' o 'Level 2'?
¿Cuántas ventanas más tiene 'Level 2' que 'Level 1'?
¿Qué porcentaje de todas las puertas está en 'Level 2'?
¿Cuántas habitaciones de 'Level 1' miden más de 10 m²?
¿Cuál es la longitud total de los muros en 'Level 1' en metros?
¿Cuál es la longitud total de los muros en 'Level 1' en pies?
Si cada puerta cuesta 450 euros, ¿cuánto cuestan todas las puertas de 'Level 1'?
¿Cuál es la superficie de la habitación más grande en 'Level 2'?
¿Cuántos pilares hay en 'Level 1'?
¿Cuál es el volumen total de las losas del modelo?
¿Cuántas ventanas hay en 'Erdgeschoss'?
¿Cuál es la superficie total de las habitaciones de 'Dachgeschoss'?
¿Cuántas veces mayor es la superficie de las habitaciones de 'Erdgeschoss' que la de 'Dachgeschoss'?
¿Cuántas habitaciones hay en total en 'Erdgeschoss' y 'Dachgeschoss'?""",
"cs": """Kolik dveří je v podlaží 'Level 1'?
Kolik oken má celý model?
Jaká je celková čistá podlahová plocha všech místností v podlaží 'Level 2'?
Jaká je průměrná plocha místnosti v podlaží 'Level 1'?
Které podlaží má více dveří, 'Level 1' nebo 'Level 2'?
O kolik více oken má 'Level 2' než 'Level 1'?
Kolik procent všech dveří je v podlaží 'Level 2'?
Kolik místností v podlaží 'Level 1' je větších než 10 m²?
Jaká je celková délka stěn v podlaží 'Level 1' v metrech?
Jaká je celková délka stěn v podlaží 'Level 1' ve stopách?
Pokud každé dveře stojí 450 eur, kolik stojí všechny dveře v podlaží 'Level 1'?
Jaká je plocha největší místnosti v podlaží 'Level 2'?
Kolik sloupů je v podlaží 'Level 1'?
Jaký je celkový objem stropních desek v modelu?
Kolik oken je v podlaží 'Erdgeschoss'?
Jaká je celková plocha místností v podlaží 'Dachgeschoss'?
Kolikrát větší je plocha místností podlaží 'Erdgeschoss' než podlaží 'Dachgeschoss'?
Kolik místností je celkem v podlažích 'Erdgeschoss' a 'Dachgeschoss'?""",
"hu": """Hány ajtó van a 'Level 1' szinten?
Hány ablak van az egész modellben?
Mekkora a 'Level 2' szinten lévő összes helyiség nettó alapterülete összesen?
Mekkora a helyiségek átlagos területe a 'Level 1' szinten?
Melyik szinten van több ajtó, a 'Level 1' vagy a 'Level 2' szinten?
Mennyivel több ablak van a 'Level 2' szinten, mint a 'Level 1' szinten?
Az összes ajtó hány százaléka van a 'Level 2' szinten?
Hány helyiség nagyobb 10 m²-nél a 'Level 1' szinten?
Mekkora a falak teljes hossza a 'Level 1' szinten méterben?
Mekkora a falak teljes hossza a 'Level 1' szinten lábban?
Ha minden ajtó 450 euróba kerül, mennyibe kerül az összes ajtó a 'Level 1' szinten?
Mekkora a legnagyobb helyiség területe a 'Level 2' szinten?
Hány oszlop van a 'Level 1' szinten?
Mekkora a födémek teljes térfogata a modellben?
Hány ablak van az 'Erdgeschoss' szinten?
Mekkora a helyiségek teljes területe a 'Dachgeschoss' szinten?
Hányszor nagyobb az 'Erdgeschoss' helyiségeinek területe, mint a 'Dachgeschoss' helyiségeié?
Hány helyiség van összesen az 'Erdgeschoss' és a 'Dachgeschoss' szinten?""",
"sv": """Hur många dörrar finns på 'Level 1'?
Hur många fönster har hela modellen?
Vad är den totala nettogolvarean för alla rum på 'Level 2'?
Vad är den genomsnittliga rumsarean på 'Level 1'?
Vilket våningsplan har flest dörrar, 'Level 1' eller 'Level 2'?
Hur många fler fönster har 'Level 2' än 'Level 1'?
Hur många procent av alla dörrar finns på 'Level 2'?
Hur många rum på 'Level 1' är större än 10 m²?
Vad är väggarnas totala längd på 'Level 1' i meter?
Vad är väggarnas totala längd på 'Level 1' i fot?
Om varje dörr kostar 450 euro, vad kostar alla dörrar på 'Level 1'?
Vad är arean för det största rummet på 'Level 2'?
Hur många pelare finns på 'Level 1'?
Vad är den totala volymen av bjälklagen i modellen?
Hur många fönster finns på 'Erdgeschoss'?
Vad är den totala rumsarean på 'Dachgeschoss'?
Hur många gånger större är rumsarean på 'Erdgeschoss' än på 'Dachgeschoss'?
Hur många rum finns det sammanlagt på 'Erdgeschoss' och 'Dachgeschoss'?""",
}
ROWS = [(lang, i, q) for lang, block in Q.items() for i, q in enumerate(block.splitlines())]
assert all(len(b.splitlines()) == 18 for b in Q.values())
