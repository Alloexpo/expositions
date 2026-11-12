# Outils d'Alloexpo

- `hebdo.py`, `ajouter.py`, `CONSIGNES.md` : recherche hebdomadaire automatique (voir CONSIGNES.md). `etat.json` mémorise ce qui est connu, écarté et déjà vu.
- `scan.py`, `sources.py` : fonctions de comparaison de titres et de lecture des sites (utilisées par hebdo.py).
- Le site : `index.html` (page publique, générée), `admin.html` (page Admin), `admin.js` (décisions prises dans la page Admin), `data.json` (fiches lues par la page Admin), `img/` (affiches).

Mise à jour mensuelle (faite par Claude avec l'Excel de sauvegarde, outils stockés dans l'onglet caché `_Générateur`) :
`import_hebdo` → `apply_admin` → recherche → `maj.py` → `gen.build` + `gen.split_assets` → `export_data` + `export_etat` → `deploy_github.py … reset`.
