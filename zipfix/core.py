#!/usr/bin/env python3
"""Zip_Fixer core — ported from Systems/Zip_Fixer/zipfix.py (2026-10-10) into the CS team screen.
RESOLUTION LOGIC IS UNCHANGED (parse_street, classify, resolve, fix_bad, verify_customer_zip, needs_review).
What differs from the Mac CLI: credentials from env, a bounded disk cache, thread-local run state, run_brand()
returning structured pieces instead of writing files, per-order error isolation, Shopify token expiry.
Read-only against Shopify. Sources: liors.co.il + zips.co.il (house by house), 48shops, internal search.
Levels: EXACT_2SRC · EXACT · NEAREST · STREET · LOCALITY · SEARCH · WEB · CITY_APPROX · NONE."""
import argparse, datetime, difflib, html, json, os, re, struct, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request, zlib
from collections import OrderedDict

STORES = {'velora': 'x0mb1s-jv', 'rozela': 'achq3j-nj', 'celesta': 'k8eaxk-mb',
          'apexmen': 'qz1gzf-ss', 'selera': 'cirurt-zr'}
API = '2026-10'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36'
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'lookups')   # NOT named data/: deploy/render_deploy.py push ignores every dir called data
LOCALITIES = os.path.join(DATA, 'localities.json')     # data.gov.il resource 5c78e9fa… (שם_ישוב / לועזי)
LOCS48 = os.path.join(DATA, 'locs48.json')              # 48shops: כל היישובים + מיקוד יישוב + אוכלוסייה
SMALL_TOWN_POP = 15000                                   # מתחת = יישוב קטן → כתובת מרכזית; מעל = לפנות ללקוח
ALIASES = {'נוף הגליל': 'נצרת עילית', 'נצרת עילית': 'נוף הגליל', 'מודיעין': 'מודיעין-מכבים-רעות',
           'תל אביב': 'תל אביב - יפו', 'יפו': 'תל אביב - יפו', 'פתח תקוה': 'פתח תקווה', 'עוספיה': 'עספיא',
           'קבוצת שילר': 'גן שלמה', 'שילר': 'גן שלמה', 'kvutzat shiller': 'גן שלמה', 'shiller': 'גן שלמה',
           'הרצליה פיתוח': 'הרצליה', 'tel aviv': 'תל אביב - יפו', 'modiin': 'מודיעין-מכבים-רעות'}
Q = lambda s: urllib.parse.quote(s, safe='')


# Per-job state. The original was one process per run; here jobs are threads of one server, so the two pieces of
# mutable run state (fuzzy-guess ledger, web-search circuit breaker) are thread-local: a job never sees another job's.
class _TLSet:
    def __init__(self): self._tl = threading.local()
    def _s(self):
        if not hasattr(self._tl, 's'): self._tl.s = set()
        return self._tl.s
    def add(self, x): self._s().add(x)
    def clear(self): self._s().clear()
    def __iter__(self): return iter(list(self._s()))
    def __len__(self): return len(self._s())


# ---------------- http + cache ----------------
class BoundedCache:
    """Disk-backed page cache: values zlib-compressed in memory, insertion-ordered eviction past max_bytes, atomic
    whole-file writes (temp + fsync + rename) at most once a minute (and on force). Single binary file, so a
    crash can never leave a half-written cache in place. A corrupt/truncated file is read up to the damage."""
    MAGIC = b'ZFC1'

    def __init__(self, path, max_bytes):
        self.path, self.max_bytes = path, max_bytes
        self._d, self._bytes = OrderedDict(), 0
        self._lock = threading.RLock()
        self._loaded, self._dirty, self._last_save = False, False, 0.0
        self._save_lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._loaded: return
            self._loaded = True
            self._last_save = time.time()
            try:
                with open(self.path, 'rb') as f:
                    if f.read(4) != self.MAGIC: return
                    while True:
                        h = f.read(8)
                        if len(h) < 8: break
                        kl, vl = struct.unpack('>II', h)
                        k, v = f.read(kl), f.read(vl)
                        if len(k) < kl or len(v) < vl: break
                        self._put(k.decode('utf-8'), v)
            except (OSError, struct.error, UnicodeDecodeError):
                pass

    def _put(self, k, blob):
        old = self._d.pop(k, None)
        if old is not None: self._bytes -= len(old) + len(k)
        self._d[k] = blob; self._bytes += len(blob) + len(k)
        while self._bytes > self.max_bytes and len(self._d) > 1:
            ek, ev = self._d.popitem(last=False); self._bytes -= len(ev) + len(ek)

    def __contains__(self, k):
        self._load()
        with self._lock: return k in self._d

    def __getitem__(self, k):
        self._load()
        with self._lock: blob = self._d[k]
        return json.loads(zlib.decompress(blob).decode('utf-8'))

    def __setitem__(self, k, v):
        self._load()
        blob = zlib.compress(json.dumps(v, ensure_ascii=False).encode('utf-8'), 3)
        with self._lock:
            self._put(k, blob); self._dirty = True

    def stats(self):
        with self._lock: return {'entries': len(self._d), 'bytes': self._bytes}

    def save(self, force=False):
        self._load()
        with self._lock:
            if not self._dirty and not force: return
            if not force and time.time() - self._last_save < 60: return        # a full write — once a minute, not per order
            items = list(self._d.items()); self._dirty = False; self._last_save = time.time()
        if not self._save_lock.acquire(blocking=False):                        # another thread is already writing
            with self._lock: self._dirty = True
            return
        try:
            d = os.path.dirname(self.path) or '.'
            os.makedirs(d, exist_ok=True)
            tmp = '%s.%d.%d.partial' % (self.path, os.getpid(), threading.get_ident())
            try:
                with open(tmp, 'wb') as f:
                    f.write(self.MAGIC)
                    for k, blob in items:
                        kb = k.encode('utf-8'); f.write(struct.pack('>II', len(kb), len(blob))); f.write(kb); f.write(blob)
                    f.flush(); os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    try: os.remove(tmp)
                    except OSError: pass
        except OSError:
            with self._lock: self._dirty = True                                # disk trouble must never fail a job
        finally:
            self._save_lock.release()


_c = None
_c_lock = threading.Lock()
def cache_dir(): return os.environ.get('ZIPFIX_CACHE_DIR', '/var/data/zipfix-cache')
def cache():
    global _c
    if _c is None:
        with _c_lock:
            if _c is None:
                try: mb = float(os.environ.get('ZIPFIX_CACHE_MAX_MB', '64'))
                except ValueError: mb = 64.0
                if not (8 <= mb <= 512): mb = 64.0
                _c = BoundedCache(os.path.join(cache_dir(), 'cache.zfc'), int(mb * 1024 * 1024))
    return _c

def reset_cache():
    """Tests / re-pointing ZIPFIX_CACHE_DIR."""
    global _c
    with _c_lock: _c = None

def save_cache(force=False):
    cache().save(force)

# Outbound allowlist (defence in depth: every URL is built from a fixed host + quoted path, but a public server fails closed).
ALLOWED_HOSTS = ('liors.co.il', 'zips.co.il', 'data.gov.il', 'postalcode.48shops.com', 'html.duckduckgo.com')
def host_allowed(url):
    p = urllib.parse.urlparse(url)
    h = (p.hostname or '').lower()
    return p.scheme == 'https' and (h in ALLOWED_HOSTS or any(h == d or h.endswith('.' + d) for d in ALLOWED_HOSTS)
                                    or re.fullmatch(r'[a-z0-9-]+\.myshopify\.com', h) is not None) and p.port in (None, 443)

class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl): return None                # a redirect off the allowlist is an error, not a hop
        return super().redirect_request(req, fp, code, msg, headers, newurl)

_opener = urllib.request.build_opener(_SafeRedirect)
_last = {}
_last_lock = threading.Lock()
def http(url, data=None, headers=None, timeout=30):
    if not host_allowed(url): return 0, ''
    host = urllib.parse.urlparse(url).netloc
    with _last_lock: wait = 0.6 - (time.time() - _last.get(host, 0))
    if wait > 0: time.sleep(wait)
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, **(headers or {})})
    for attempt in (1, 2):
        try:
            with _opener.open(req, timeout=timeout) as r:
                return r.status, r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except (urllib.error.URLError, OSError) as e:      # ניתוק / timeout — ניסיון חוזר אחד, ואז "אין תשובה"
            if attempt == 2 or data is not None and 'myshopify' in url and 'graphql' not in url:
                return 0, ''
            time.sleep(3)
        finally:
            with _last_lock: _last[host] = time.time()
    return 0, ''

def page(url):
    """GET עם מטמון (כולל 404 — כדי לא לחזור עליו)."""
    c = cache(); k = 'GET|' + url
    if k not in c:
        s, t = http(url)
        if s not in (200, 404):
            return s, ''           # תקלה זמנית — לא נכנסת למטמון
        c[k] = [s, t if s == 200 else '']
    return c[k]

def text(h):
    h = re.sub(r'(?s)<script.*?</script>|<style.*?</style>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h))).strip()


# ---------------- shopify ----------------
class ZipfixConfigError(RuntimeError):
    pass

def kc(brand, name):
    """Shopify read-only app credentials. Render: env SHOPIFY_CLIENT_ID_<BRAND> / SHOPIFY_CLIENT_SECRET_<BRAND>.
    On the Mac (CLI) the cs-engine Keychain is the fallback."""
    v = os.environ.get(f'{name}_{brand.upper()}', '').strip()
    if v: return v
    try:
        return subprocess.check_output(['security', 'find-generic-password', '-s', 'cs-engine', '-a', f'{brand}/{name}', '-w'],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        raise ZipfixConfigError(f'missing {name}_{brand.upper()}')

TOKEN_TTL_S = 20 * 3600            # Shopify client-credentials tokens live 24 h
_tok = {}
_tok_lock = threading.Lock()
def _token(brand, fresh=False):
    with _tok_lock:
        t = _tok.get(brand)
        if fresh or not t or time.time() - t[1] > TOKEN_TTL_S:
            body = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': kc(brand, 'SHOPIFY_CLIENT_ID'),
                                           'client_secret': kc(brand, 'SHOPIFY_CLIENT_SECRET')}).encode()
            st, tx = http(f'https://{STORES[brand]}.myshopify.com/admin/oauth/access_token', body,
                          {'Content-Type': 'application/x-www-form-urlencoded'})
            try: tok = json.loads(tx)['access_token']
            except (ValueError, KeyError, TypeError):
                raise RuntimeError(f'{brand}: shopify token request failed (http {st})')
            _tok[brand] = t = (tok, time.time())
        return t[0]

def gql(brand, q, v=None):
    for attempt in (1, 2):
        st, t = http(f'https://{STORES[brand]}.myshopify.com/admin/api/{API}/graphql.json',
                     json.dumps({'query': q, 'variables': v or {}}).encode(),
                     {'Content-Type': 'application/json', 'X-Shopify-Access-Token': _token(brand, fresh=attempt == 2)})
        if st in (401, 403) and attempt == 1: continue            # token expired / rotated → one fresh token
        break
    try: d = json.loads(t)
    except ValueError:
        raise RuntimeError(f'{brand}: shopify answered http {st} without JSON')
    if d.get('errors'):
        raise RuntimeError(f'{brand}: {d["errors"]}')
    return d['data']

OQ = '''query($q:String,$after:String){orders(first:100,after:$after,reverse:true,query:$q){
 pageInfo{hasNextPage endCursor}
 edges{node{name createdAt shippingAddress{city address1 address2 zip countryCodeV2}}}}}'''

def fetch(brand, numbers=None, query='fulfillment_status:unfulfilled status:open'):
    if numbers:
        query = ' OR '.join(f'name:#{n.lstrip("#")}' for n in numbers)
    out, after = [], None
    while True:
        d = gql(brand, OQ, {'q': query, 'after': after})['orders']
        for e in d['edges']:
            n = e['node']; a = n.get('shippingAddress') or {}
            out.append({'brand': brand, 'order': n['name'], 'created': n['createdAt'][:10],
                        'city': (a.get('city') or '').strip(), 'address1': (a.get('address1') or '').strip(),
                        'address2': (a.get('address2') or '').strip(), 'zip': norm_zip(a.get('zip')),
                        'country': a.get('countryCodeV2')})
        if not d['pageInfo']['hasNextPage']:
            return out
        after = d['pageInfo']['endCursor']


# ---------------- parsing ----------------
def norm_zip(z):
    d = re.sub(r'\D', '', z or '')
    return d if len(d) == 7 else None

CYR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
               ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','sh','','y','','e','yu','ya']))
ARB = dict(zip('ابتثجحخدذرزسشصضطظعغفقكلمنهوية',
               ['a','b','t','t','j','h','kh','d','d','r','z','s','sh','s','d','t','z','','g','f','q','k','l','m','n','h','u','i','a']))
AR_CITY = {'القدس': 'ירושלים', 'الناصرة': 'נצרת', 'حيفا': 'חיפה', 'يافا': 'תל אביב - יפו', 'عكا': 'עכו',
           'ام الفحم': 'אום אל-פחם', 'أم الفحم': 'אום אל-פחם', 'رهط': 'רהט', 'الطيبة': 'טייבה', 'الطيرة': 'טירה',
           'شفاعمرو': 'שפרעם', 'سخنين': "סח'נין", 'طمرة': 'טמרה', 'باقة الغربية': 'באקה אל-גרביה', 'كفر قاسم': 'כפר קאסם',
           'قلنسوة': 'קלנסווה', 'عرابة': 'עראבה', 'جلجولية': "ג'לג'וליה", 'بيت صفافا': 'ירושלים', 'كفر كنا': 'כפר כנא'}

def latinize(t):
    """רוסית/ערבית → לטינית, כדי שיעברו במסלול האנגלי (שלד עיצורים מול הרשימה הממשלתית)."""
    if not t or not re.search(r'[\u0400-\u04ff\u0600-\u06ff]', t): return t
    t = re.sub(r'(?i)\b(ул|улица|пр|проспект|бульвар|шдерот|рехов)\.?\s*', '', t)
    out = []
    for ch in t:
        lo = ch.lower()
        out.append(CYR.get(lo, ARB.get(ch, ch)) if (lo in CYR or ch in ARB) else ch)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()

CUT = r'(?:^|(?<=[\s,.]))(דירה|ד\'(?=[\s\d]|$)|קומה|קומת|כניסה|קרקע|בית פרטי|בית\s*$|ת\.\s*ד\.?|ת\.ד|תד(?=[\s\d])|תיבת דואר|apt|apartment|floor|dira|entrance|po box|על\d)(?=[\s\d,.:]|$)'

def parse_street(a1, city=None):
    """כתובת חופשית → (רחוב, מספר בית). הבית = המספר הראשון אחרי מילות הרחוב; כל מה שאחריו (דירה, קומה,
    "41 41", שם העיר, "בית פרטי") נזרק. גם מספר לפני הרחוב ("40, שמעון בן צבי"), עיר בתחילת הכתובת,
    רוסית/ערבית (latinize), ו"Bar nisan13"."""
    s = latinize(a1 or '').replace('׳', "'").replace('״', '"').replace('ּ', '')
    if city: city = latinize(city)
    s = re.sub(r'[֑-ׇ]', '', s)
    s = re.sub(r'(?<=[A-Za-zא-ת])[-/]?(?=\d)|(?<=\d)(?=[A-Za-zא-ת]{2})', ' ', s)
    for c in sorted(filter(None, {city, hebrew_city(city) if city else None}), key=len, reverse=True):
        for v in {c, c.replace('-', ' ')}:
            s = re.sub(r'(^|[\s,.])' + re.escape(v) + r'(?=$|[\s,.])', ' ', s, flags=re.I)
    while True:                                               # "דירה 10 קומה 3 …" בתחילת השדה — נמחק כולו
        m0 = re.match(r'\s*' + CUT + r'\s*\d*[א-ת]?\s*[,.]?', s, flags=re.I)
        if not m0 or not m0.group(0).strip(): break
        s = s[m0.end():]
    m = re.search(CUT, s, flags=re.I)
    if m and m.start() > 2: s = s[:m.start()]                 # דירה/קומה אחרי הכתובת — נחתך
    elif m: s = s[:m.start()] + s[m.end():]                   # "קרקע 57/7, לאה אמנו" — רק המילה יוצאת
    s = re.sub(r'(?i)(^|\s)(רח\'?|רחוב|רח\.|street|st\.?|str\.?)(?=\s|$)', ' ', s)
    toks = [t for t in re.split(r'[\s,]+', s.strip(' .,-')) if t and t not in ('.', '-', '/')]
    isnum = lambda t: re.fullmatch(r'\d+[א-תa-zA-Z]?[\'"׳]?(?:[/\\-]\S*)?', t)
    isword = lambda t: re.search(r'[A-Za-zא-ת]{2,}', t) and not re.search(r'\d', t)
    words, num, lead = [], None, False
    for t in toks:
        if isword(t):
            if num and words and not lead: break
            words.append(t.strip('.'))
        elif isnum(t):
            n = re.match(r'\d+', t).group(0)
            if not words and num is None: num, lead = n, True        # "40, שמעון בן צבי"
            elif words and not lead: num = n; break                   # "הכלנית 16 …"
            elif words and lead: break                                # "9 ברוריה, 1" — 1 היא דירה
        elif words:
            break
    street = ' '.join(words).strip(' ,.') or None
    return street, num

def classify(o):
    if o['country'] and o['country'] != 'IL':
        return 'NOT_IL'
    street, num = parse_street(o['address1'], o['city'])
    if not o['city'] or not street or not re.search(r'[א-תa-zA-Z]', street):
        return 'BAD_ADDRESS'
    return 'OK' if o['zip'] else 'MISSING_ZIP'


# ---------------- city / street normalization ----------------
def _key(s):
    s = re.sub(r'["\'״׳`.\-–־()]', ' ', s or '').replace('קריית', 'קרית')
    return re.sub(r'\s+', ' ', s).strip().lower()

def _sq(s):
    return re.sub(r'[\s\'"`’׳״\-–־().]|^אל', '', (s or '').replace('קריית', 'קרית').replace('אל-', '').replace(' אל ', ' '))

def _lat(s):
    return re.sub(r'[^a-z]', '', (s or '').lower()).replace('k', 'c').replace('q', 'c').replace('y', 'i').replace('ee', 'i')

_locs = None
def localities():
    global _locs
    if _locs is None:
        if not os.path.exists(LOCALITIES):
            _, t = http('https://data.gov.il/api/3/action/datastore_search?resource_id=5c78e9fa-c2e2-4771-93ff-7f400a12f7ba&limit=5000')
            json.dump(json.loads(t)['result']['records'], open(LOCALITIES, 'w'), ensure_ascii=False)
        _locs = [(r['שם_ישוב'].strip(), (r['שם_ישוב_לועזי'] or '').strip()) for r in json.load(open(LOCALITIES))]
    return _locs

_l48 = None
def locs48():
    """{שם: (מיקוד יישוב 7 ספרות, אוכלוסייה)} מכל עמודי הטבלה של 48shops (נשמר לקובץ)."""
    global _l48
    if _l48 is None:
        _l48 = _locs48_load()
    return _l48

def _locs48_load():
    if os.path.exists(LOCS48):
        return json.load(open(LOCS48))
    out, n = {}, 0
    while True:
        st, t = http(f'https://postalcode.48shops.com/Default.aspx?ln=hebrew&page={n}&region=0&s=')
        rows = re.findall(r"<td><a href='City\.aspx\?ln=hebrew&id=\d+'>([^<]+)</a>\s*(?:<span class='CssMorePC'>\+(\d+)</span>)?</td><td><span class='CssCP'>(\d{5})<b>(\d{2})</b></span></td><td>[^<]*</td><td>(\d*)</td>", t)
        if st != 200 or not rows or (n and rows[0][0] in out): break
        for name, more, a, b, pop in rows:
            out[html.unescape(name).strip()] = [a + b, int(pop) if pop else 0, int(more or 0) + 1]   # [מיקוד, אוכלוסייה, כמה מיקודים]
        n += 1
    tmp = LOCS48 + '.partial'; json.dump(out, open(tmp, 'w'), ensure_ascii=False); os.replace(tmp, LOCS48)
    return out

FUZZY = _TLSet()   # (סוג, קלט, תוצאה) — כל החלפת שם בניחוש פאזי. נשלח לבדיקה, לא ישר לספקית.
def loc_lookup(city):
    L = locs48(); keys = {_key(k): k for k in L}
    for c in [city, ALIASES.get(city, '')]:
        if c and _key(c) in keys: return keys[_key(c)], L[keys[_key(c)]]
    sq = {_sq(k): k for k in L}
    for c in [city, ALIASES.get(city, '')]:
        if c and _sq(c) in sq: return sq[_sq(c)], L[sq[_sq(c)]]
    base = re.sub(r'^(כפר|כפר-)\s*', '', city.strip())
    for k in L:
        parts = [p.strip() for p in re.split(r'[-–]', k)]
        if len(parts) > 1 and any(_sq(p) in (_sq(city), _sq(base)) for p in parts): return k, L[k]
    m = difflib.get_close_matches(_sq(city), list(sq), n=1, cutoff=0.8)
    if m: FUZZY.add(('loc', city, sq[m[0]]))                  # "חריש"→"חורפיש" — ניחוש, לא התאמה
    return (sq[m[0]], L[sq[m[0]]]) if m else (None, None)

def hebrew_city(city):
    """עיר כפי שהלקוח כתב → שם רשמי בעברית, או None. סדר: מדויק → כינוי → שם יישוב בתחילת המחרוזת
    ("עפולה גבעת המורה") → יישוב שמתחיל במחרוזת, הכי מאוכלס ("מודיעין") → פאזי קשוח."""
    raw = (city or '').strip()
    for k, v in AR_CITY.items():
        if k in raw: return v
    c = re.sub(r'^\s*(קיבוץ|מושב|יישוב|ישוב)\s+(?=\S)', '', latinize(raw))
    c = re.sub(r'(?i)^\s*(moshav|moshab|kibbutz|kibutz)\.?\s+', '', c)
    c = re.sub(r'(?i)^\s*(moshav|moshab|kibbutz|kibutz)\.?\s+', '', c)
    if not c: return None
    if re.search(r'[א-ת]', c):
        names = {_key(h): h for h, _ in localities()}
        names.update({_key(h): h for h in locs48() if _key(h) not in names})
        sq = {_sq(n): n for n in names.values()}
        for v in (c, ALIASES.get(c), ALIASES.get(_key(c))):
            if v and _key(v) in names: return names[_key(v)]
            if v and _sq(v) in sq: return sq[_sq(v)]
        if _key(c) in ALIASES: return ALIASES[_key(c)]
        w = _key(c).split()
        for i in range(len(w) - 1, 0, -1):                      # שם יישוב + שכונה
            pre = ' '.join(w[:i])
            if pre in names: return names[pre]
            if ALIASES.get(pre): return ALIASES[pre]
        pop = lambda n: (locs48().get(n) or [0, 0])[1]
        starts = [n for k, n in names.items() if re.match(re.escape(_key(c)) + r'[\s]', k + ' ') and k != _key(c)]
        starts = [n for n in starts if re.match(re.escape(_key(c)) + r'(\s|$)', _key(n))]
        if starts: return max(starts, key=pop)
        m = difflib.get_close_matches(_sq(c), list(sq), n=1, cutoff=0.88)
        if m: FUZZY.add(('city', raw, sq[m[0]]))
        return sq[m[0]] if m else c
    lc = re.sub(r'\b(kibbutz|moshav|kvutzat|kvutza|kfar)\b', '', c, flags=re.I).strip()
    for v in (c.lower(), lc.lower()):
        if v in ALIASES: return ALIASES[v]
    lat = {_lat(e): h for h, e in localities() if e}
    for i, v in enumerate((c, lc, lc.split()[0] if lc.split() else '')):
        m = difflib.get_close_matches(_lat(v), list(lat), n=1, cutoff=0.75)
        if m:
            if i == 2 or difflib.SequenceMatcher(None, _lat(v), m[0]).ratio() < 0.85:   # "Rishon …"→"רשפון"
                FUZZY.add(('city', raw, lat[m[0]]))
            return lat[m[0]]
    return None

def slug(s):
    return re.sub(r'\s+', '-', re.sub(r'["\'״׳]', '', s.strip()))

def city_slugs(city):
    out = [slug(city), slug(city.replace('קריית', 'קרית')), slug(city.replace('קרית', 'קריית'))]
    if city in ALIASES: out.append(slug(ALIASES[city]))
    if ' - ' in city or '-' in city:
        out.append(slug(re.split(r'\s*-\s*', city)[0]))
    out.append(slug(city.replace(' - ', ' ')))
    return list(dict.fromkeys(out))

STREETS_GOV = os.path.join(DATA, 'streets_gov.json')   # data.gov.il 9ad3862c… — כל רחובות ישראל לפי יישוב
_sg = None
def gov_streets(city):
    global _sg
    if _sg is None:
        _sg = {_key(k): v for k, v in json.load(open(STREETS_GOV)).items()} if os.path.exists(STREETS_GOV) else {}
    return [re.sub(r'\s+', ' ', x) for x in _sg.get(_key(city), [])]

def liors_city(city):
    """→ (slug, [street names], streets_count) או None."""
    for s in city_slugs(city):
        st, t = page(f'https://liors.co.il/{Q("מיקוד")}/{Q(s)}/')
        if st == 200 and t:
            names = [urllib.parse.unquote(l).rstrip('/').split('/')[-1].replace('-', ' ')
                     for l in re.findall(r'href="https://liors\.co\.il/[^"]+/' + re.escape(Q(s)) + r'/([^"/]+)/"', t)]
            names = [n for n in dict.fromkeys(names) if n]
            return s, names, len(names)
    return None

HE = {'ב': 'B', 'ג': 'G', 'ד': 'D', 'ה': 'H', 'ז': 'Z', 'ח': 'H', 'ט': 'T', 'כ': 'K', 'ך': 'K', 'ל': 'L', 'מ': 'M',
      'ם': 'M', 'נ': 'N', 'ן': 'N', 'ס': 'S', 'פ': 'P', 'ף': 'P', 'צ': 'Z', 'ץ': 'Z', 'ק': 'K', 'ר': 'R', 'ש': 'X', 'ת': 'T'}
def skel_he(s):
    out = []
    for w in re.findall(r'[א-ת]+', s):
        w = re.sub(r'ה$', '', w) if len(w) > 2 else w
        out.append(''.join(HE.get(ch, '') for ch in w))
    return ''.join(out)

def skel_en(s):
    s = s.lower()
    for a, b in (('sch', 'X'), ('sh', 'X'), ('ch', 'H'), ('kh', 'H'), ('tz', 'Z'), ('ts', 'Z'), ('ph', 'P'), ('th', 'T')):
        s = s.replace(a, b)
    out = []
    for w in re.findall(r'[a-zXHZPT]+', s):
        w = re.sub(r'h$', '', w) if len(w) > 2 else w
        out.append(''.join({'b': 'B', 'v': 'B', 'w': 'B', 'g': 'G', 'j': 'G', 'd': 'D', 'h': 'H', 'z': 'Z', 't': 'T',
                            'k': 'K', 'c': 'K', 'q': 'K', 'l': 'L', 'm': 'M', 'n': 'N', 's': 'S', 'p': 'P', 'f': 'P',
                            'r': 'R', 'x': 'X'}.get(ch, ch if ch in 'XHZPT' else '') for ch in w))
    return ''.join(out)

TYPE_WORDS = r'^((דרך|שדרות|שד|סמטת|סמ|שביל|כיכר|ככר|רחוב|רח|הרב|רבי|רב|ד"ר|דר|פרופ\'?|derech|sderot|shderot|rehov|rechov|st|street|harav|rabbi)\.?\s+)+'
def strip_type(n):
    return re.sub(TYPE_WORDS, '', (n or '').strip(), flags=re.I)

def match_street(street, names):
    if not re.search(r'[א-ת]', street) and re.search(r'[A-Za-z]', street):
        sk = skel_en(re.sub(r'(?i)\b(rav|harav|rabbi|dr|prof|st|street|alley|ave|road|rd)\b\.?', ' ', street)); cands = {}
        for n in names:
            for v in (n, strip_type(n)):
                cands.setdefault(skel_he(v), n)
                w = v.split()
                if len(w) > 1:
                    for rot in (list(reversed(w)), w[1:] + w[:1], w[-1:] + w[:-1]):
                        cands.setdefault(skel_he(' '.join(rot)), n)
        if sk in cands: return cands[sk], 0.9
        ok = [k for k in cands if abs(len(k) - len(sk)) <= 1]   # אורך כמעט זהה — לא "בר גיורא"→"גורג בראק"
        m = difflib.get_close_matches(sk, ok, n=1, cutoff=0.85)
        return (cands[m[0]], 0.8) if m else (None, 0)
    k = _key(strip_type(street)) or _key(street)
    keys = {_key(n): n for n in names}
    for n in names:
        keys.setdefault(_key(strip_type(n)), n)
        w = _key(strip_type(n)).split()
        if len(w) > 1: keys.setdefault(' '.join(reversed(w)), n)
    if k in keys: return keys[k], 1.0
    for alt in (k[1:] if k.startswith('ה') else 'ה' + k, k.replace('שדרות ', ''), k.replace('דרך ', '')):
        if alt in keys: return keys[alt], 0.95
    best = None
    for cand in keys:
        if abs(len(cand) - len(k)) > 1: continue
        if (len(k) >= 4 and _lev1(k, cand)) or difflib.SequenceMatcher(None, k, cand).ratio() >= 0.88:
            best = cand; break
    if best: return keys[best], difflib.SequenceMatcher(None, k, best).ratio()
    return None, 0

def _lev1(a, b):
    """מרחק עריכה ≤1 (טעות הקלדה אחת): "המלקוק"→"המלקוש", לא "הערבה"→"העבודה"."""
    if a == b: return True
    if abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b): return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b): a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:]: return True
    return False


# ---------------- sources ----------------
def liors_street(cslug, street):
    st, t = page(f'https://liors.co.il/{Q("מיקוד")}/{Q(cslug)}/{Q(slug(street))}/')
    if st != 200: return None
    rows = re.findall(r'<tr><td>([^<]*)</td><td class="zip">(\d{7})</td></tr>', t)
    return {h.strip(): z for h, z in rows}

def zips_street(cslug, street):
    st, t = page(f'https://zips.co.il/street/{Q(cslug)}/{Q(slug(street))}')
    if st != 200: return None
    x = text(t)
    out = {}
    for h, z in re.findall(r'רחוב [^\d]{1,40}? (\d+(?: ?[א-ט](?![א-ת]))?) מיקוד (\d{7})', x):   # "70 א" = בית נפרד
        out.setdefault(h.replace(' ', ''), z)
    return out

def zips_search(q):
    st, t = page('https://zips.co.il/search?q=' + Q(q))
    if st != 200: return []
    return [(a.strip(), z) for a, z in re.findall(r"([^'|]{3,60}?) - מיקוד (\d{7})", text(t))]


def nearest(table, num, suffix=None):
    """→ (מיקוד, בית). בית עם אות ("70א") — מפתח מדויק אם קיים; אחרת הבית עצמו; אחרת הקרוב באותו צד."""
    if not table or num is None: return None, None
    table = {k: v for k, v in table.items() if not v.endswith('0000')}   # מיקוד כללי ≠ מיקוד בית (zips בביתר עילית)
    if suffix:
        for k, z in table.items():
            if re.sub(r'[\s\'"׳]', '', k) == f'{num}{suffix}' and not z.endswith('000'): return z, int(num)
    nums = {}
    for h, z in table.items():
        m = re.match(r'^(\d+)', h)
        if m and (int(m.group(1)) not in nums or re.fullmatch(r'\d+', h.strip())):
            nums[int(m.group(1))] = z                          # בית בלי אות גובר על "70א"
    if not nums: return None, None
    n = int(num)
    if n in nums: return nums[n], n
    same = [h for h in nums if h % 2 == n % 2] or list(nums)
    h = min(same, key=lambda x: abs(x - n))
    return nums[h], h

def resolve(city_raw, address1, address2=''):
    """→ dict(zip, level, city, street, house, note)."""
    street, num = parse_street(address1, city_raw)
    if street and not num and address2:                       # "יהואש" + שורה 2 "22" / "9/26" / "25 קומה 2 דירה 7"
        st2, n2 = parse_street(address2, city_raw)
        if n2 and (not st2 or re.match(JUNK, _key(st2), flags=re.I)): num = n2
    suffix = None                                              # "70א" — לבית עם אות יש מיקוד משלו
    if num:
        m = re.search(rf'(?<!\d){num}\s*([א-ט])(?![א-ת])', f'{address1} {address2 or ""}')
        if m: suffix = m.group(1)
    city = hebrew_city(city_raw) if city_raw else None
    res = {'zip': None, 'level': 'NONE', 'city': city, 'street': street, 'house': num, 'note': ''}
    if not city:
        res['note'] = 'עיר לא מזוהה'; return res
    lc = liors_city(city)
    if lc and street:
        cslug, names, _ = lc
        st_name, score = match_street(street, names)
        if st_name:
            res['street'] = st_name
            a, b = liors_street(cslug, st_name) or {}, zips_street(cslug, st_name) or {}
            za, ha = nearest(a, num, suffix); zb, hb = nearest(b, num, suffix)
            ea, eb = bool(num and za and ha == int(num)), bool(num and zb and hb == int(num))
            if ea and eb and za == zb:
                res.update(zip=za, level='EXACT_2SRC')
            elif ea and eb:
                res.update(zip=zb, level='CONFLICT', note=f'liors {za} / zips {zb}', alt=za)
            elif ea or eb:
                res.update(zip=za if ea else zb, level='EXACT')
            elif za or zb:
                res.update(zip=za or zb, level='NEAREST', note=f'בית {ha or hb} הכי קרוב')
            elif a.get('—'):
                res.update(zip=a['—'], level='STREET')
                for cs in city_slugs(city):
                    zb2, hb2 = nearest(zips_street(cs, st_name) or {}, num, suffix)
                    if zb2:
                        res.update(zip=zb2, level='EXACT' if num and hb2 == int(num) else 'NEAREST'); break
            if score < 1.0:
                res['note'] = (res['note'] + f' · רחוב תוקן מ-"{street}"').strip(' ·')
            if res['zip']: return res
    # liors לא מכיר את העיר/הרחוב → שם רשמי מרשימת הרחובות הממשלתית → דף הרחוב של zips
    if street:
        cand = []
        gs = gov_streets(city)
        mname, _ = match_street(street, gs) if gs else (None, 0)
        if mname: cand.append(mname)
        if re.search(r'[א-ת]', street): cand.append(street)
        for nm in dict.fromkeys(cand):
            for cs in city_slugs(city):
                b = zips_street(cs, nm)
                if b:
                    zb, hb = nearest(b, num, suffix)
                    if zb:
                        exact = bool(num) and hb == int(num)
                        res.update(zip=zb, street=nm, level='EXACT' if exact else 'NEAREST',
                                   note=('' if exact else f'בית {hb} הכי קרוב') + (f' · רחוב תוקן מ-"{street}"' if nm != street else ''))
                        return res
    # חיפוש חופשי (zips.co.il) — רחוב+מספר+עיר
    if street:
        hits = [z for a, z in zips_search(f'{street} {num or ""} {city}'.replace('  ', ' ')) if _key(city.split()[0]) in _key(a)]
        if hits:
            res.update(zip=hits[0], level='SEARCH', note='חיפוש חופשי'); return res
    # מיקוד היישוב (יישוב עם מיקוד יחיד / מעט מיקודים)
    name, v = loc_lookup(city)
    if v and (v[2] <= 3 or (v[1] and v[1] < SMALL_TOWN_POP)):     # יישוב קטן → מיקוד היישוב (גיא)
        res.update(zip=v[0], level='LOCALITY'); return res
    if not v and not liors_city(city) and len(gov_streets(city)) <= 40:   # יישוב שלא בטבלה → חיפוש מיקוד היישוב
        w = web_zip(f'מיקוד {city}', city)
        if w:
            res.update(zip=w, level='LOCALITY', note='מיקוד יישוב מחיפוש ברשת'); return res
    # חיפוש ברשת — לא מפסיקים לחפור
    if street:
        w = web_zip(f'מיקוד {street} {num or ""} {city}', city)
        words = [x for x in _key(strip_type(res['street'] or street)).split() if len(x) > 2 and re.search(r'[א-ת]', x)]
        if w and words and any(all(x in _key(a) for x in words) and _key(city).split()[0] in _key(a) for a, _ in reverse(w)):
            res.update(zip=w, level='WEB', note='חיפוש ברשת, אומת בחיפוש הפוך'); return res
    # מוצא אחרון: מיקוד כלשהו של העיר — "קרוב", מסומן לבדיקה
    name, v = loc_lookup(city)
    if v:
        res.update(zip=v[0], level='CITY_APPROX', note=f'מיקוד כללי של {name} ({v[2]} מיקודים בעיר)'); return res
    res['note'] = 'לא נמצא'; return res

_wf = threading.local()
class _WebFail:
    def __getitem__(self, i): return getattr(_wf, 'n', 0)
    def __setitem__(self, i, v): _wf.n = v
_web_fail = _WebFail()
def web_zip(q, city):
    c = cache(); k = 'WEB|' + q
    if k not in c:
        if _web_fail[0] >= 2: return None                 # מפסק: החיפוש חוסם/איטי — לא מעכבים את כל הריצה
        time.sleep(2)
        st, t = http('https://html.duckduckgo.com/html/?q=' + Q(q), timeout=12)
        if st != 200:
            _web_fail[0] += 1; return None
        _web_fail[0] = 0
        c[k] = [text(x) for x in re.findall(r'(?s)class="result__snippet"[^>]*>(.*?)</a>', t)]
    votes = {}
    for sn in c[k]:
        if _key(city).split()[0] not in _key(sn): continue
        for zc in re.findall(r'(?<!\d)(\d{7})(?!\d)', sn):
            votes[zc] = votes.get(zc, 0) + 1
    return max(votes, key=votes.get) if votes else None

def locality_zip(city, lc=None):
    name, v = loc_lookup(city)
    if v and (len(v) < 3 or v[2] <= 3): return v[0]
    lc = lc or liors_city(city)
    if lc and lc[1]:
        t = liors_street(lc[0], lc[1][0]) or {}
        if t.get('—'): return t['—']
    hits = [z for a, z in zips_search(city) if _key(city) in _key(a)]
    if hits: return hits[0]
    m = re.search(r'(\d{5})', text(page(f'https://liors.co.il/{Q("מיקוד")}/{Q(slug(city))}/')[1] or ''))
    return (m.group(1) + '00') if m else None

def reverse(zipc):
    """מיקוד → [(כתובת, מיקוד)]"""
    return [(a, z) for a, z in zips_search(zipc) if z == zipc]

def town_pop(city):
    name, v = loc_lookup(city) if city else (None, None)
    return v[1] if v else None


# ---------------- commands ----------------
def brands(arg): return [arg] if arg else list(STORES)

JUNK = r'^(דירה|ד|קומה|קרקע|בית|בית פרטי|פרטי|כניסה|ת\.?ד|מספר|מס|number|no|apt|apartment|floor|house|d+|א|ב|ג|na|n/a|none|-+)$'
NUMBERED_CITIES = {'אילת', 'נצרת'}          # כתובת = מספר בניין/רחוב ("5076", "רחוב 5097") — כתובת תקינה

def _street_ok(st, city):
    if not st or not re.search(r'[A-Za-zא-ת]{2,}', st): return False
    k = _key(st)
    if re.match(JUNK, k, flags=re.I): return False
    for c in filter(None, {city, hebrew_city(city) if city else None}):
        if k == _key(c) or _sq(st) == _sq(c): return False          # "נצרת" / "קיבוץ אלמוג" ברחוב
    return True

def from_context(o, city):
    """הכתובת האמיתית מתוך כל השדות: שורה 2 · שורה 1+2 · מספר משורה אחת ורחוב מהשנייה."""
    a1, a2 = o['address1'] or '', o['address2'] or ''
    num_only = lambda t: (re.match(r'^\s*(\d+)', t) or [None, None])[1]
    for text, extra in ((a2, a1), (f'{a1} {a2}', ''), (f'{a2} {a1}', ''), (a1, a2)):
        st, n = parse_street(text, o['city'])
        if _street_ok(st, o['city']):
            n = n or num_only(extra) or num_only(a1)
            return st, n
    return None, None

def fix_bad(o):
    """כתובת לא תקינה → כתובת למשלוח. סדר: הקשר בהזמנה → מיקוד שנכתב בשדה → עיר עם מספרי בניינים
    → כתובת לפי מיקוד הלקוח (לא ממיקוד יישוב כללי) → יישוב קטן + מספר → לפנות ללקוח."""
    city = hebrew_city(o['city']) if o['city'] else None
    fields = f"{o['address1'] or ''} {o['address2'] or ''}"
    # 1. הרחוב נמצא בשדה אחר
    st, n = from_context(o, o['city'])
    if city and st:
        r = resolve(o['city'], f'{st} {n or ""}'.strip())
        off = r.get('street') or ''
        same = _key(strip_type(off)) == _key(strip_type(st)) or _lev1(_key(strip_type(off)), _key(strip_type(st)))
        name = off if off and re.search(r'[א-ת]', off) and (same or not re.search(r'[א-ת]', st)) else st
        if r['level'] in ('EXACT_2SRC', 'EXACT', 'CONFLICT', 'NEAREST', 'STREET', 'LOCALITY') or re.search(r'[א-ת]', st):
            return {'action': 'FROM_CONTEXT', 'address': f'{name} {n or ""}'.strip(), 'zip': r['zip'] or o['zip'],
                    'level': r['level'], 'city': city}
    # 2. מיקוד שנכתב בתוך שדה הכתובת ("20200" בשפרעם)
    if not o['zip']:
        for m in re.findall(r'(?<!\d)(\d{7}|\d{5})(?!\d)', fields):
            z7 = m if len(m) == 7 else m + '00'
            name, v = loc_lookup(city) if city else (None, None)
            if v and v[0][:5] == z7[:5]:
                o = {**o, 'zip': z7}; break
    # 3. עיר שבה הכתובת היא מספר בניין/רחוב
    if city in NUMBERED_CITIES:
        m = re.search(r'(?<!\d)(\d{3,5})(?!\d)', fields)
        if m:
            hits = [z for a, z in zips_search(f'{m.group(1)} {city}') if city in a]
            zc = o['zip'] or (hits[0] if hits else None) or (loc_lookup(city)[1] or [None])[0]
            rest = re.search(re.escape(m.group(1)) + r'\s*/\s*(\d+)', fields)
            label = (f'בניין {m.group(1)}' + (f' דירה {rest.group(1)}' if rest else '')) if city == 'אילת' \
                else (f'רחוב {m.group(1)}' + (f' {rest.group(1)}' if rest else ''))
            return {'action': 'NUMBERED', 'address': label, 'zip': zc,
                    'level': 'EXACT' if hits else 'CITY_APPROX', 'city': city}
    # 4. כתובת לפי המיקוד — רק מיקוד של כתובת, לא מיקוד יישוב כללי (שמחזיר "בשור 0")
    if o['zip']:
        hits = reverse(o['zip'])
        real = [(a, z) for a, z in hits if not re.search(r'\s0\s*,', a)]
        if real:
            num = (re.match(r'^\s*(\d+)', o['address1'] or '') or [None, None])[1]
            same = [a for a, _ in real if num and re.search(rf'(?<!\d){num}(?!\d)', a)]
            full = same[0] if same else real[0][0]
            parts = [x.strip() for x in full.split(',')]
            return {'action': 'FROM_ZIP', 'address': parts[0], 'zip': o['zip'], 'level': 'EXACT',
                    'city': parts[1] if len(parts) > 1 and not city else city}
    # 5. יישוב קטן → שם היישוב + מספר הבית מכל שדה
    pop = town_pop(city)
    if city and pop is not None and pop < SMALL_TOWN_POP:
        name, _ = loc_lookup(city)
        n = (re.search(r'(?<!\d)(\d{1,4})(?!\d)', fields) or [None, None])[1]
        return {'action': 'SMALL_TOWN', 'address': f"{name or city} {n or ''}".strip(),
                'zip': o['zip'] or locality_zip(city), 'level': 'LOCALITY', 'city': name or city}
    return {'action': 'ASK_CUSTOMER', 'address': None, 'zip': None, 'level': 'NONE', 'city': city}


def verify_customer_zip(o):
    """מיקוד שהלקוח הזין: נשאר אם הוא שייך לכתובת שלו (חיפוש הפוך) או שאין לנו תשובה טובה יותר.
    מוחלף רק כשהמיקוד שלו שייך לכתובת אחרת / לא קיים, ויש לנו תשובה ברמת הבית."""
    street, num = parse_street(o['address1'], o['city'])
    rv = reverse(o['zip'])
    words = [w for w in _key(strip_type(street or '')).split() if len(w) > 1]
    if rv and any(w in _key(a) for a, _ in rv for w in words):
        return {'zip': o['zip'], 'level': 'CUSTOMER_OK', 'note': ''}
    r = resolve(o['city'], o['address1'], o['address2'])
    if r['zip'] and r['level'] in ('EXACT_2SRC', 'EXACT', 'CONFLICT') and r['zip'] != o['zip']:
        r['note'] = (f"הלקוח כתב {o['zip']} — " + (f'שייך ל-{rv[0][0]}' if rv else 'לא קיים במאגר') + ' · ' + r['note']).strip(' ·')
        r['level'] = 'CUSTOMER_FIXED'
        return r
    return {'zip': o['zip'], 'level': 'CUSTOMER_KEPT', 'note': 'לא אומת, אין תשובה טובה יותר'}


def needs_review(o, r):
    """סיבה לבדיקה של ארז, או None. רק מסמן — לא משנה מיקוד."""
    why = {'CITY_APPROX': 'רחוב לא במאגר — מיקוד כללי של העיר', 'WEB': 'נמצא בחיפוש ברשת',
           'CUSTOMER_FIXED': 'הוחלף מיקוד שהלקוח הזין', 'CONFLICT': 'שני מקורות חלוקים — נבחר zips',
           'STREET': 'בלי מספר בית — מיקוד ברירת מחדל של הרחוב'}.get(r.get('level'))
    if why: return why
    for kind, raw, got in FUZZY:
        if raw in (o.get('city'), (o.get('city') or '').strip()) and kind in ('city', 'loc'):
            return f'שם היישוב נוחש: "{raw}" → "{got}"'
    if 'תוקן' in (r.get('note') or ''): return 'שם הרחוב תוקן בניחוש'
    m = re.search(r'בית (\d+) הכי קרוב', r.get('note') or '')
    if m and r.get('house') and abs(int(m.group(1)) - int(r['house'])) > 10:
        return f'הבית הכי קרוב רחוק ({m.group(1)} במקום {r["house"]})'
    return None

def _order_key(o):
    m = re.search(r'\d+', o['order'])
    return int(m.group(0)) if m else 0

def _addr(o):
    return ' '.join(x for x in (o.get('address1') or '', o.get('address2') or '') if x).strip()

def fetch_many(brand, nums=None, chunk=40):
    """fetch() in chunks of order numbers (a Shopify search query with hundreds of OR terms is not safe)."""
    if not nums:
        return fetch(brand, None)
    out = []
    for i in range(0, len(nums), chunk):
        out += fetch(brand, nums[i:i + chunk])
    return out

def run_brand(brand, nums=None, progress=None):
    """Same logic as the original run(), but returns the pieces instead of writing files.
    supplier_text = exactly what is pasted to the supplier (zip lines sorted by order number, then the
    'Order #N address:' blocks). review / ask_customer are NOT for the supplier. progress(done, total)."""
    FUZZY.clear(); _web_fail[0] = 0
    prog = progress or (lambda d, t: None)
    orders = fetch_many(brand, nums)
    total = len(orders); prog(0, total)
    zl, bad, failed = [], [], []
    for i, o in enumerate(orders, 1):
        try:
            c = classify(o)
            if c == 'MISSING_ZIP':
                zl.append((o, resolve(o['city'], o['address1'], o['address2'])))
            elif c == 'BAD_ADDRESS':
                bad.append((o, fix_bad(o)))
            elif c == 'OK' and nums:                       # הספקית ביקשה את ההזמנה → גם מיקוד הלקוח נבדק
                zl.append((o, verify_customer_zip(o)))
        except Exception as e:                             # one odd order must not sink the batch — it goes to the human list
            failed.append((o, type(e).__name__))
        save_cache()
        prog(i, total)
    allz = [(o, r['zip']) for o, r in zl if r['zip']] + [(o, f['zip']) for o, f in bad if f.get('zip')]
    lines = [f"{o['order'].lstrip('#')} - {zc}" for o, zc in sorted(allz, key=lambda x: _order_key(x[0]))]
    ask = [o for o, r in zl if not r['zip']] + [o for o, f in bad if f['action'] == 'ASK_CUSTOMER']
    addr = []
    for o, f in bad:
        if f['action'] == 'ASK_CUSTOMER': continue
        addr += [f"Order {o['order']} address:", f"City: {f.get('city') or hebrew_city(o['city']) or o['city']}",
                 f"Zip code: {f['zip'] or ''}", f"Street and number: {f['address'] or ''}", '']
    body = '\n'.join(lines) + ('\n\n' + '\n'.join(addr) if addr else '')
    check = [(o, r, needs_review(o, r)) for o, r in zl] + [(o, f, needs_review(o, f)) for o, f in bad if f['action'] != 'ASK_CUSTOMER']
    check = [x for x in check if x[2]]
    legacy = body
    if ask or check or failed:
        legacy += '\n\n\n===== לא לשלוח לספקית — לבדיקה של ארז =====\n'
    if ask:
        legacy += '\n# לפנות ללקוח (אין דרך לדעת):\n' + '\n'.join(f"{o['order']} | {o['city']} | {o['address1']} | {o['address2']}" for o in ask) + '\n'
    if check:
        legacy += '\n# מיקוד נשלח, כדאי להעיף עין:\n' + '\n'.join(
            f"{o['order'].lstrip('#')} - {r.get('zip')} | {w} | {o['city']} | {o['address1']} {o['address2']} | {r.get('note','')}"
            for o, r, w in check)
    review = [{'order': o['order'].lstrip('#'), 'zip': r.get('zip'), 'reason': w, 'city': o['city'], 'address': _addr(o),
               'note': r.get('note', '')} for o, r, w in check]
    review += [{'order': o['order'].lstrip('#'), 'zip': None, 'reason': 'שגיאה בעיבוד ההזמנה — לבדוק ידנית', 'city': o['city'],
                'address': _addr(o), 'note': err} for o, err in failed]
    asks = [{'order': o['order'].lstrip('#'), 'city': o['city'], 'address': _addr(o)} for o in ask]
    got = {o['order'].lstrip('#') for o in orders}
    return {'brand': brand, 'supplier_text': body,
            'review': review, 'ask_customer': asks,
            'counts': {'orders': total, 'zips': len(lines), 'review': len(review), 'ask': len(asks)},
            'not_found': [n for n in (nums or []) if n.lstrip('#') not in got],
            'ran_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            '_legacy_text': legacy}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['scan', 'run', 'one'])
    ap.add_argument('args', nargs='*'); ap.add_argument('--brand'); ap.add_argument('--orders')
    a = ap.parse_args()
    nums = [x.strip().lstrip('#') for x in re.split(r'[,\s]+', a.orders) if x.strip()] if a.orders else None
    if nums and not a.brand:
        sys.exit('--orders דורש --brand: מספרי הזמנות חופפים בין חנויות (velora/apexmen באותו טווח)')
    if a.cmd == 'scan':
        for b in ([a.brand] if a.brand else list(STORES)):
            cnt = {}
            for o in fetch_many(b, nums): cnt[classify(o)] = cnt.get(classify(o), 0) + 1
            print(b, cnt)
    elif a.cmd == 'one':
        print(json.dumps(resolve(a.args[0], a.args[1]), ensure_ascii=False))
    elif a.cmd == 'run':
        for b in ([a.brand] if a.brand else list(STORES)):
            r = run_brand(b, nums)
            if r['counts']['orders'] and (r['supplier_text'] or r['review'] or r['ask_customer']):
                print(f'##### {b}'); print(r['_legacy_text'])


if __name__ == '__main__':
    try: main()
    finally: save_cache(force=True)
