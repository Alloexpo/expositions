# -*- coding: utf-8 -*-
"""Détection mensuelle des nouvelles expositions à Paris (API Paris Open Data « Que faire à Paris »).
Ajoute les nouveautés dans l'Excel avec Décision = « À valider ». Ne touche jamais aux lignes existantes."""
import re, json, copy, datetime, unicodedata, html as _html
import requests, openpyxl

API = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records"
STOP = set('de du des la le les et en a au aux un une l d sur pour dans the of and musee expo exposition'.split())
RULES_DEFAULT = ['accrochage', 'installation', 'atelier', 'visite', 'conférence', 'conference', 'concert', 'spectacle', 'projection', 'stage',
                 'rencontre', 'lecture', 'nocturne', 'collection permanente', 'on a vu', 'mon petit', 'design week', 'fashion week', 'journée d\'étude', 'colloque', 'performance', 'goûter', 'jeune public', 'en famille']
SPORT_RE = re.compile(r'\b(sports?|sportifs?|sportives?|olymp\w+|paralymp\w+|football|rugby|tennis|marathon|cyclis\w+|boxe|boxeurs?|athl[eè]\w+|gymnast\w+|natation|alpinis\w+|r[eé]gates?|arts martiaux|stades?)\b', re.I)
TAGMAP = {'photographie': 'Photographie', 'mode': 'Mode', 'street art': 'Street art', 'cinéma': 'Cinéma', 'musique': 'Musique',
          'architecture': 'Architecture et urbanisme', 'sciences': 'Sciences et techniques', 'bande dessinée': 'Bande dessinée',
          'art contemporain': 'Art contemporain', 'sculpture': 'Art moderne de transition', 'histoire': 'Histoire contemporaine (XIX-XXIe s.)'}

def norm(t):
    t = unicodedata.normalize('NFD', (t or '').lower()); t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.findall(r'[a-z0-9]+', t)
def toks(t): return {x for x in norm(t) if x not in STOP and len(x) > 1}
def clean(t):
    t = re.sub(r'<(br|/p|/li|/h\d)[^>]*>', '\n', t or ''); t = re.sub(r'<[^>]+>', ' ', t); t = _html.unescape(t).replace('\xa0', ' ')
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', t)).strip()
def words(t, n):
    w = t.split(); return t if len(w) <= n else ' '.join(w[:n]).rstrip(',;:') + '…'
def price(t):
    t = clean(t).split('\n')[0]; m = re.match(r'^De\s+([\d,]+)\s+à\s+([\d,]+)\s*(?:euros|€)', t)
    if m: return f"De {m.group(1)} à {m.group(2)} €" + (' selon les tarifs' if m.group(1) == '0' else '')
    m = re.search(r'([\d,]+)\s*(?:euros|€)', t); return f"{m.group(1)} €" if m else ''
def iso(v):
    if isinstance(v, datetime.datetime): return v.date().isoformat()
    if isinstance(v, datetime.date): return v.isoformat()
    return str(v)[:10] if v else ''

def table_rows(ws):
    h = next(i for i, r in enumerate(ws.iter_rows(max_row=12, values_only=True), 1) if r and r[0] == 'Intitulé')
    heads = [str(c.value or '').strip() for c in ws[h]]
    return h, heads
def col(heads, prefix):
    for i, x in enumerate(heads):
        if x.startswith(prefix): return i + 1

def read_rules(wb):
    if 'Règles' not in wb.sheetnames: return list(RULES_DEFAULT)
    ws = wb['Règles']; out = []
    for r in ws.iter_rows(min_row=4, max_col=1, values_only=True):
        if r[0] and str(r[0]).strip(): out.append(str(r[0]).strip().lower())
    return out or list(RULES_DEFAULT)

def ensure_rules_sheet(wb):
    if 'Règles' in wb.sheetnames: return
    ws = wb.create_sheet('Règles', 3)
    ws['A1'] = "Règles d'exclusion automatiques"; ws['A1'].font = openpyxl.styles.Font(bold=True, size=14)
    ws['A2'] = "Les nouveautés dont le titre contient l'un de ces mots ne vous sont jamais proposées. Ajoutez un mot par ligne (colonne A)."
    ws['A3'] = 'Mot ou expression à exclure'; ws['A3'].font = openpyxl.styles.Font(bold=True)
    ws['C3'] = 'Règles proposées d\'après vos rejets'; ws['C3'].font = openpyxl.styles.Font(bold=True)
    ws['D3'] = 'Validez (X)'; ws['D3'].font = openpyxl.styles.Font(bold=True)
    for i, w in enumerate(RULES_DEFAULT, 4): ws.cell(i, 1, w)
    ws.column_dimensions['A'].width = 40; ws.column_dimensions['C'].width = 48; ws.column_dimensions['D'].width = 14

def known_and_rejected(wb):
    venues, known, rej = set(), [], []
    for sh in ('Expositions', 'Archives'):
        if sh not in wb.sheetnames: continue
        ws = wb[sh]; h, heads = table_rows(ws); cT, cL, cD, cF, cDec = 1, col(heads, 'Lieu'), col(heads, 'Début'), col(heads, 'Fin'), col(heads, 'Décision')
        for r in ws.iter_rows(min_row=h + 1, values_only=True):
            if not r or not r[0]: continue
            ven = str(r[cL - 1] or '').strip()
            if ven: venues.add(ven)
            ent = (toks(str(r[0])), iso(r[cD - 1]), ven)
            if str(r[cDec - 1] or '').strip() == 'Écartée': rej.append(ent)
            else: known.append(ent)
    if '_Rejets' in wb.sheetnames:
        for r in wb['_Rejets'].iter_rows(min_row=2, values_only=True):
            if r and r[1]: rej.append((toks(str(r[1])), str(r[0]).split('|')[-1], str(r[2] or '')))
    return venues, known, rej

def sameven(x, y):
    a, b = ' '.join(norm(x)), ' '.join(norm(y))
    return bool(a) and bool(b) and (a == b or a.startswith(b + ' ') or b.startswith(a + ' '))

def venue_match(name, venues):
    a = ' '.join(norm(name))
    if not a: return None
    pref = [v for v in venues if (lambda b: a == b or b.startswith(a + ' ') or a.startswith(b + ' '))(' '.join(norm(v)))]
    if pref: return max(pref, key=len)            # nom le plus complet (celui que vous avez complété)
    best = None
    for v in venues:
        ta, tb = toks(name), toks(v)
        if ta and tb:
            j = len(ta & tb) / max(len(ta), len(tb))
            if j >= 0.8 and (best is None or j > best[0]): best = (j, v)
    return best[1] if best else None

def same(a, b, window=75):
    ta, da = a[0], a[1]; tb, db = b[0], b[1]
    if not ta or not tb: return False
    ov = len(ta & tb) / min(len(ta), len(tb))
    try: dd = abs((datetime.date.fromisoformat(da) - datetime.date.fromisoformat(db)).days)
    except Exception: dd = 0
    if ov >= 0.75 and dd <= window: return True
    if ov >= 0.9 and min(len(ta), len(tb)) >= 2 and dd <= 450: return True       # même titre, dates aberrantes de l'API
    sv = len(a) > 2 and len(b) > 2 and sameven(a[2], b[2])
    if sv and dd <= 20 and any(len(t) >= 7 for t in ta & tb): return True        # même lieu, même début, mot-clé commun
    if sv and dd <= 7 and ov >= 0.6: return True
    return False

def fetch(today, horizon=420):
    end = today + datetime.timedelta(days=horizon); out, off = [], 0
    where = f'qfap_tags like "Expo" AND date_end >= date\'{today.isoformat()}\' AND date_start <= date\'{end.isoformat()}\''
    while off < 2000:
        for _ in range(3):
            try:
                r = requests.get(API, params={'limit': 100, 'offset': off, 'where': where, 'order_by': 'date_start'}, timeout=60)
                if r.status_code == 200: break
            except Exception: r = None
        if not r or r.status_code != 200: break
        res = r.json().get('results', []); out += res
        if len(res) < 100: break
        off += 100
    return out

def scan(wb, today=None):
    today = today or datetime.date.today(); ensure_rules_sheet(wb)
    rules = read_rules(wb); venues, known, rej = known_and_rejected(wb)
    recs = fetch(today); seen = set(); new = []; stats = dict(api=len(recs), deja_connues=0, rejetees=0, regles=0, trop_courtes=0, lieu_non_suivi={}, ajoutees=0)
    for x in recs:
        title = (x.get('title') or '').strip()
        if not title or x['id'] in seen: continue
        seen.add(x['id'])
        try:
            d0 = datetime.datetime.fromisoformat(x['date_start']).date(); d1 = datetime.datetime.fromisoformat(x['date_end']).date()
        except Exception: continue
        if (d1 - d0).days < 14 or d1 < today + datetime.timedelta(days=10) or (d1 - d0).days > 450:
            stats['trop_courtes'] += 1; continue
        title = re.sub(r'^(Exposition|Expo)\s*:?\s*', '', title, flags=re.I).strip()
        m = re.match(r'^(?:à|au)\s+[^:«"]{3,40}:\s*[«"“]\s*(.+?)\s*[»"”]?$', title)
        if m: title = m.group(1)
        title = re.sub(r'\s+(?:au|à la|à l[\'’])\s*(?:Musée|Cité|Galerie|Palais)\b.*$', '', title).strip()
        title = re.sub(r'[«»“”"]', '', title); title = re.sub(r'\s+', ' ', title); title = re.sub(r'\s+\.', '.', title).strip(' .') or title
        if any(w in title.lower() for w in rules): stats['regles'] += 1; continue
        ven = venue_match(x.get('address_name') or '', venues)
        if not ven:
            n = x.get('address_name') or '?'; stats['lieu_non_suivi'][n] = stats['lieu_non_suivi'].get(n, 0) + 1; continue
        ent = (toks(title), d0.isoformat(), ven)
        if any(same(ent, k) for k in known) or any(same(ent, k, 400) for k in [e for e in rej]):
            stats['rejetees' if any(same(ent, k, 400) for k in rej) else 'deja_connues'] += 1; continue
        if any(same(ent, (toks(n['t']), n['a'], n['l'])) for n in new): continue
        tags = [t.strip().lower() for t in (x.get('qfap_tags') or '').split(';')]
        tag1 = next((TAGMAP[t] for t in tags if t in TAGMAP), 'Autres et inclassables')
        if SPORT_RE.search(title + ' ' + clean(x.get('lead_text'))): tag1 = 'Sports'
        lead = clean(x.get('lead_text')); body = [p for p in clean(x.get('description')).split('\n') if len(p) > 60 and p[:40] not in lead]
        txt = lead if len(lead) >= 150 or not body else lead + ' ' + body[0]
        al = x.get('access_link') or ''
        new.append(dict(t=title, l=ven, a=d0.isoformat(), b=d1.isoformat(), tag=tag1, re=words(txt, 150), px=price(x.get('price_detail')),
                        pg=al if al and not re.match(r'^https?://[^/]+/?$', al) else (x.get('url') or ''), im=x.get('cover_url') or '',
                        bk=al, src=x.get('url') or ''))
    stats['ajoutees'] = len(new); return new, stats

def append_rows(wb, rows, today=None):
    today = today or datetime.date.today(); ws = wb['Expositions']; h, heads = table_rows(ws)
    c = {k: col(heads, k) for k in ['Intitulé', 'Lieu', 'Ville', 'Tag 1', 'Tag 2', 'Début', 'Fin', 'Statut', 'Jours restants', 'Ouvre dans', 'Tarif', 'Durée', "Page de l'exposition", 'Résumé', 'Image', 'Décision', 'Remarques', 'Billetterie (statut)', 'Billetterie (lien)']}
    last = max(r for r in range(h + 1, ws.max_row + 1) if ws.cell(r, 1).value)
    for n in rows:
        last += 1; r = last
        for cc in range(1, ws.max_column + 1):
            ws.cell(r, cc)._style = copy.copy(ws.cell(last - 1, cc)._style)
        ws.row_dimensions[r].height = ws.row_dimensions[last - 1].height
        ws.cell(r, c['Intitulé'], n['t']); ws.cell(r, c['Lieu'], n['l']); ws.cell(r, c['Ville'], n.get('v') or 'Paris'); ws.cell(r, c['Tag 1'], n['tag'])
        if n.get('tag2'): ws.cell(r, c['Tag 2'], n['tag2'])
        ws.cell(r, c['Début'], datetime.date.fromisoformat(n['a'])); ws.cell(r, c['Fin'], datetime.date.fromisoformat(n['b']))
        D, F, S = openpyxl.utils.get_column_letter(c['Début']), openpyxl.utils.get_column_letter(c['Fin']), openpyxl.utils.get_column_letter(c['Statut'])
        ws.cell(r, c['Statut'], f'=IF({F}{r}<TODAY(),"Terminée",IF({D}{r}>TODAY(),"À venir","En cours"))')
        ws.cell(r, c['Jours restants'], f'=IF({S}{r}="En cours",{F}{r}-TODAY(),"")'); ws.cell(r, c['Ouvre dans'], f'=IF({S}{r}="À venir",{D}{r}-TODAY(),"")')
        ws.cell(r, c['Tarif'], n['px'] or None); ws.cell(r, c['Durée'], n.get('dur') or '1 h 30'); ws.cell(r, c['Résumé'], n['re']); ws.cell(r, c['Image'], n['im'] or None)
        if n['pg']: ws.cell(r, c["Page de l'exposition"], n['pg']).hyperlink = n['pg']
        ws.cell(r, c['Décision'], 'À valider')
        ws.cell(r, c['Remarques'], f"Nouveauté détectée le {today.strftime('%d/%m/%Y')}" + (f" (source : {n['src']})" if n.get('src') and not str(n.get('src')).startswith('http') else '') + " : tags et durée à vérifier")
        ws.cell(r, c['Billetterie (statut)'], 'À vérifier')
        if n['bk']: ws.cell(r, c['Billetterie (lien)'], n['bk'])
        for k in ('Intitulé', 'Lieu', 'Ville', 'Tarif', 'Résumé', 'Image', "Page de l'exposition", 'Billetterie (lien)', 'Remarques'):
            x = ws.cell(r, c[k])                             # texte venu d'Internet : jamais interprété comme une formule Excel
            if isinstance(x.value, str) and x.value[:1] in '=+-@': x.data_type = 's'
        for k in ('Image', "Page de l'exposition", 'Billetterie (lien)'):
            x = ws.cell(r, c[k])
            if x.value and not re.match(r'^https?://', str(x.value), re.I): x.value = None; x._hyperlink = None
    return len(rows)

def propose_rules(wb):
    """Mots récurrents dans les titres que vous avez rejetés (et absents des titres que vous gardez) -> onglet Règles, colonne C."""
    ensure_rules_sheet(wb); ws = wb['Règles']
    _, known, rej = known_and_rejected(wb)
    kept = set().union(*[k[0] for k in known]) if known else set()
    cnt = {}
    for r in rej:
        for t in r[0]:
            if len(t) >= 5 and t not in kept: cnt[t] = cnt.get(t, 0) + 1
    props = sorted([t for t, n in cnt.items() if n >= 2])
    have = {str(ws.cell(i, 3).value).strip() for i in range(4, ws.max_row + 1) if ws.cell(i, 3).value}
    r = 4
    while ws.cell(r, 3).value: r += 1
    for t in props:
        if t not in have: ws.cell(r, 3, t); r += 1
    return props
