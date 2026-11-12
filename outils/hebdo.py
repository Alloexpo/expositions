# -*- coding: utf-8 -*-
"""Alloexpo — recherche hebdomadaire des nouvelles expositions (sans IA : uniquement de la collecte et du tri).
Usage : python3 outils/hebdo.py   → écrit outils/candidats.json (seulement ce qui n'a JAMAIS été vu) et met à jour outils/etat.json.
Tout ce qui a déjà été examiné (adresse dans etat['vus']) n'est ni retéléchargé ni reproposé."""
import sys, os, re, json, types, datetime, html as _html, urllib.parse, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
try: import openpyxl  # noqa
except Exception: sys.modules['openpyxl'] = types.ModuleType('openpyxl')
import requests, scan, sources
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36', 'Accept-Language': 'fr-FR,fr;q=0.9'}
S = requests.Session(); S.headers.update(UA)
URL_RE = re.compile(r'/expositions-musees/[a-z0-9-]+-\d+/[a-z0-9-]+-\d+\.html')
MAXC = int(os.environ.get('ALLOEXPO_MAX', '12'))
MOIS = {'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12}
def get(u, t=25):
    try:
        r = S.get(u, timeout=t)
        return r if r.status_code == 200 else None
    except Exception: return None
def html_to_text(t): return _html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', t, flags=re.S))))

def parse_fr_dates(text):
    m = re.search(r'\bdu\s+(\d{1,2})(?:er)?\s*(\w+)?\s*(\d{4})?\s+au\s+(\d{1,2})(?:er)?\s+(\w+)\s+(\d{4})', text, re.I)
    if not m: return None, None
    d1d, d1m, d1y = int(m.group(4)), MOIS.get(m.group(5).lower()), int(m.group(6))
    if not d1m: return None, None
    d0d = int(m.group(1)); d0m = MOIS.get((m.group(2) or '').lower()) or d1m; d0y = int(m.group(3)) if m.group(3) else d1y
    if not m.group(3) and d0m > d1m: d0y = d1y - 1
    try: return datetime.date(d0y, d0m, d0d), datetime.date(d1y, d1m, d1d)
    except Exception: return None, None

def jload(p, d):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return d
def main():
    today = datetime.date.today()
    etat = jload(os.path.join(HERE, 'etat.json'), {}); data = jload(os.path.join(ROOT, 'data.json'), {'items': []})
    vus = dict(etat.get('vus') or {})
    adm = {}
    try:
        m = re.search(r'window\.ADM\s*=\s*(\{.*\})\s*;?\s*$', open(os.path.join(ROOT, 'admin.js'), encoding='utf-8').read(), re.S); adm = json.loads(m.group(1)) if m else {}
    except Exception: pass
    E = lambda t, a, l: (scan.toks(t), a, l or '')
    known = [E(*k) for k in etat.get('connus', [])] + [E(i['t'], i['a'], i.get('l')) for i in data.get('items', [])] + [E(n.get('t', ''), n.get('a', ''), n.get('l')) for n in adm.get('a', [])]
    rej = [E(*k) for k in etat.get('rejets', [])] + [E(i.rsplit('|', 1)[0], i.rsplit('|', 1)[-1], '') for i in adm.get('x', [])]
    rules = [r.lower() for r in etat.get('regles', [])]; excl = re.compile(etat.get('exclus') or r'^$'); cands = []; stats = dict(offi_nouvelles=0, regions_nouvelles=0, deja_vues=0)
    def keep(t, a, b, l):
        if b < today + datetime.timedelta(days=10) or a > today + datetime.timedelta(days=420) or (b - a).days < 14: return False
        if any(w in t.lower() for w in rules): return False
        e = E(t, a.isoformat(), l)
        return not (any(scan.same(e, k) for k in known) or any(scan.same(e, k, 400) for k in rej) or any(scan.same(e, E(c['t'], c['a'], c['l'])) for c in cands))
    for c in etat.get('attente') or []:           # candidats trouvés une semaine précédente mais pas encore présentés
        try:
            if keep(c['t'], datetime.date.fromisoformat(c['a']), datetime.date.fromisoformat(c['b']), c['l']): cands.append(c)
        except Exception: pass
    # 1. Officiel des spectacles (Paris et Île-de-France)
    def month(mm, yy):
        out = set()
        for n in range(1, 15):
            r = get(f"https://www.offi.fr/expositions-musees/mois-{mm:02d}-{yy}.html" + (f"?npage={n}" if n > 1 else ""))
            if not r: break
            s = set(URL_RE.findall(r.text))
            if not s or s <= out: break
            out |= s
        return out
    ms = [((today.month - 1 + i) % 12 + 1, today.year + (today.month - 1 + i) // 12) for i in range(11)]
    with cf.ThreadPoolExecutor(6) as ex: urls = set().union(*ex.map(lambda a: month(*a), ms))
    new = sorted(u for u in urls if u not in vus); stats['deja_vues'] += len(urls) - len(new); stats['offi_nouvelles'] = len(new)
    def offi(u):
        r = get('https://www.offi.fr' + u)
        if not r: return None
        t = r.text; g = lambda p: _html.unescape((re.search(p, t) or [None, ''])[1])
        ti = re.sub(r"\s*\|\s*L'Officiel.*$", '', g(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"')); ti = re.sub(r'^Exposition\s+', '', ti)
        parts = re.split(r'\s+-\s+', ti); title = parts[0].strip(); lieu = parts[1].strip() if len(parts) > 1 else u.split('/')[2]
        d0, d1 = parse_fr_dates(t)
        if not d0: d0, d1 = parse_fr_dates(html_to_text(t))
        x = html_to_text(t); i = x.find('Présentation'); pres = re.split(r"(Œuvres exposées|L'exposition .{0,160}est référencée|Derniers avis)", x[i + 12:i + 1400])[0].strip() if i >= 0 else ''
        px = (re.findall(r'Tarifs?\s*:\s*([^.]{0,80})', x) or [''])[0].strip()
        return dict(u=u, t=title, l=lieu, d0=d0, d1=d1, im=g(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"'), txt=pres[:700], px=px, slug=u.split('/')[2])
    with cf.ThreadPoolExecutor(8) as ex: res = list(ex.map(offi, new))
    for u, x in zip(new, res):
        if not x: continue                      # échec réseau : on réessaiera la semaine suivante
        vus[u] = today.isoformat()
        if not x['d0'] or not x['d1'] or not x['t'] or excl.search(x['slug']): continue
        if keep(x['t'], x['d0'], x['d1'], x['l']):
            cands.append(dict(t=x['t'], l=x['l'], v='Paris ou Île-de-France (à préciser)', a=x['d0'].isoformat(), b=x['d1'].isoformat(), source='https://www.offi.fr' + u, im=x['im'], px=x['px'], txt=x['txt']))
    # 2. Sources en régions et hors Paris (sites des musées, offices de tourisme)
    lieux = etat.get('lieux', {})
    for s in etat.get('sources', []):
        h = sources.fetch(s['url'])
        if not h: continue
        try: motif = re.compile(s.get('motif') or r'expo', re.I)
        except re.error: continue
        links = []
        for m in re.finditer(r'href="([^"#]+)"', h):
            u = urllib.parse.urljoin(s['url'], _html.unescape(m.group(1)))
            if u.startswith('http') and motif.search(u) and u.rstrip('/') != s['url'].rstrip('/') and u not in links: links.append(u)
        links = links[:30]; fresh = [u for u in links if u not in vus]; stats['deja_vues'] += len(links) - len(fresh); stats['regions_nouvelles'] += len(fresh)
        for u in fresh:
            d = sources.detail(u)
            if not d: continue
            vus[u] = today.isoformat()
            if not d['title'] or not d['d0']: continue
            ven = s.get('lieu')
            if not ven:
                c = [v for v in lieux.get(s['ville'], []) if v and v.lower() in d['text'].lower()]; ven = max(c, key=len) if c else None
            if not ven: continue
            title = re.sub(r'^(Exposition|Expo)\s*:?\s*', '', d['title'], flags=re.I).strip()
            if len(title) < 4 or re.fullmatch(r"(?i)(les )?(év[èée]nements?|expositions?( en cours| à venir| temporaires| passées)?|agenda|programme|programmation|accueil.*|actualités?|à venir|en ce moment|bienvenue.*)", title): continue
            if keep(title, d['d0'], d['d1'], ven):
                cands.append(dict(t=title, l=ven, v=s['ville'], a=d['d0'].isoformat(), b=d['d1'].isoformat(), source=u, im=d['img'], px='', txt=(d['desc'] or d['text'][:700])[:700]))
    reste = max(0, len(cands) - MAXC); etat['attente'] = cands[MAXC:]; cands = cands[:MAXC]
    cut = (today - datetime.timedelta(days=500)).isoformat(); etat['vus'] = {u: d for u, d in vus.items() if d >= cut}; etat['derniere_recherche'] = today.isoformat()
    json.dump(etat, open(os.path.join(HERE, 'etat.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump(cands, open(os.path.join(HERE, 'candidats.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(dict(candidats=len(cands), en_attente_pour_la_prochaine_fois=reste, **stats), ensure_ascii=False))
if __name__ == '__main__': main()
