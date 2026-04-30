#!/usr/bin/env python3
"""
Networked terminal chess game.
Usage:
  Host:   python chess.py host [port]
  Client: python chess.py join <host_ip> [port]
"""

import socket
import threading
import sys
import os
import json
import time

# ── Board constants ────────────────────────────────────────────────────────────

EMPTY = "."
W, B = "w", "b"

PIECES = {
    "wK": "♔", "wQ": "♕", "wR": "♖", "wB": "♗", "wN": "♘", "wP": "♙",
    "bK": "♚", "bQ": "♛", "bR": "♜", "bB": "♝", "bN": "♞", "bP": "♟",
    EMPTY: " ",
}

# ANSI colours
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
BG_LIGHT = "\033[48;5;180m"
BG_DARK  = "\033[48;5;94m"
BG_SEL   = "\033[48;5;28m"
BG_MOVE  = "\033[48;5;22m"

DEFAULT_PORT = 55000

# ── Board setup ────────────────────────────────────────────────────────────────

def make_board():
    b = [[EMPTY] * 8 for _ in range(8)]
    order = ["R","N","B","Q","K","B","N","R"]
    for i, p in enumerate(order):
        b[0][i] = "b" + p
        b[7][i] = "w" + p
    for i in range(8):
        b[1][i] = "bP"
        b[6][i] = "wP"
    return b

# ── Rendering ──────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def render(board, my_color, selected=None, valid_moves=None, msg="", last_move=None):
    clear()
    valid_set  = set(valid_moves) if valid_moves else set()
    last_set   = set(last_move)   if last_move   else set()

    flip = (my_color == B)
    rows = range(7, -1, -1) if not flip else range(8)
    cols = range(8)         if not flip else range(7, -1, -1)

    col_labels = "  " + "  ".join(chr(ord("a") + c) for c in cols)
    print(BOLD + CYAN + col_labels + RESET)

    for r in rows:
        rank_label = str(r + 1)
        row_str = BOLD + CYAN + rank_label + " " + RESET
        for c in cols:
            piece = board[r][c]
            is_light = (r + c) % 2 == 0

            if selected and (r, c) == selected:
                bg = BG_SEL
            elif (r, c) in valid_set:
                bg = BG_MOVE
            elif (r, c) in last_set:
                bg = BG_SEL
            elif is_light:
                bg = BG_LIGHT
            else:
                bg = BG_DARK

            symbol = PIECES.get(piece, "?")
            row_str += bg + " " + symbol + " " + RESET
        row_str += BOLD + CYAN + " " + rank_label + RESET
        print(row_str)

    print(BOLD + CYAN + col_labels + RESET)
    print()
    if msg:
        print(msg)

# ── Move generation ────────────────────────────────────────────────────────────

def color_of(piece):
    return piece[0] if piece != EMPTY else None

def is_enemy(piece, color):
    return piece != EMPTY and color_of(piece) != color

def in_bounds(r, c):
    return 0 <= r < 8 and 0 <= c < 8

def raw_moves(board, r, c, en_passant=None):
    piece = board[r][c]
    if piece == EMPTY:
        return []
    color = piece[0]
    kind  = piece[1]
    moves = []

    def slide(dr, dc):
        nr, nc = r + dr, c + dc
        while in_bounds(nr, nc):
            if board[nr][nc] == EMPTY:
                moves.append((nr, nc))
            elif is_enemy(board[nr][nc], color):
                moves.append((nr, nc))
                break
            else:
                break
            nr += dr; nc += dc

    if kind == "R":
        for d in [(1,0),(-1,0),(0,1),(0,-1)]: slide(*d)
    elif kind == "B":
        for d in [(1,1),(1,-1),(-1,1),(-1,-1)]: slide(*d)
    elif kind == "Q":
        for d in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]: slide(*d)
    elif kind == "N":
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if in_bounds(nr,nc) and color_of(board[nr][nc]) != color:
                moves.append((nr,nc))
    elif kind == "K":
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr==0 and dc==0: continue
                nr, nc = r+dr, c+dc
                if in_bounds(nr,nc) and color_of(board[nr][nc]) != color:
                    moves.append((nr,nc))
    elif kind == "P":
        fwd = 1 if color == B else -1
        start_row = 1 if color == B else 6
        nr = r + fwd
        if in_bounds(nr, c) and board[nr][c] == EMPTY:
            moves.append((nr, c))
            if r == start_row:
                nr2 = r + 2*fwd
                if in_bounds(nr2, c) and board[nr2][c] == EMPTY:
                    moves.append((nr2, c))
        for dc in [-1, 1]:
            nc = c + dc
            if in_bounds(nr, nc):
                target = board[nr][nc]
                if is_enemy(target, color):
                    moves.append((nr, nc))
                elif en_passant and (nr, nc) == en_passant:
                    moves.append((nr, nc))
    return moves

def find_king(board, color):
    for r in range(8):
        for c in range(8):
            if board[r][c] == color + "K":
                return (r, c)
    return None

def is_in_check(board, color):
    kr, kc = find_king(board, color)
    opp = B if color == W else W
    for r in range(8):
        for c in range(8):
            if color_of(board[r][c]) == opp:
                if (kr, kc) in raw_moves(board, r, c):
                    return True
    return False

def apply_move(board, fr, fc, tr, tc, en_passant=None, promotion="Q"):
    import copy
    nb = copy.deepcopy(board)
    piece = nb[fr][fc]
    nb[tr][tc] = piece
    nb[fr][fc] = EMPTY
    color = piece[0]
    kind  = piece[1]
    new_ep = None

    if kind == "P":
        fwd = 1 if color == B else -1
        if abs(fr - tr) == 2:
            new_ep = ((fr + tr) // 2, fc)
        if en_passant and (tr, tc) == en_passant:
            nb[tr - fwd][tc] = EMPTY
        if (color == W and tr == 0) or (color == B and tr == 7):
            nb[tr][tc] = color + promotion
    return nb, new_ep

def legal_moves(board, r, c, en_passant=None):
    piece = board[r][c]
    if piece == EMPTY:
        return []
    color = piece[0]
    moves = []
    for (tr, tc) in raw_moves(board, r, c, en_passant):
        nb, _ = apply_move(board, r, c, tr, tc, en_passant)
        if not is_in_check(nb, color):
            moves.append((tr, tc))
    return moves

def all_legal_moves(board, color, en_passant=None):
    moves = []
    for r in range(8):
        for c in range(8):
            if color_of(board[r][c]) == color:
                for (tr, tc) in legal_moves(board, r, c, en_passant):
                    moves.append((r, c, tr, tc))
    return moves

def is_checkmate(board, color, en_passant=None):
    return len(all_legal_moves(board, color, en_passant)) == 0 and is_in_check(board, color)

def is_stalemate(board, color, en_passant=None):
    return len(all_legal_moves(board, color, en_passant)) == 0 and not is_in_check(board, color)

# ── Castling ───────────────────────────────────────────────────────────────────

def castle_moves(board, color, castling_rights):
    moves = []
    row = 7 if color == W else 0
    king_sq = (row, 4)
    if board[row][4] != color + "K":
        return moves
    if is_in_check(board, color):
        return moves
    opp = B if color == W else W

    def sq_attacked(r, c):
        for rr in range(8):
            for cc in range(8):
                if color_of(board[rr][cc]) == opp:
                    if (r,c) in raw_moves(board, rr, cc):
                        return True
        return False

    # Kingside
    if castling_rights.get(color + "K"):
        if board[row][5] == EMPTY and board[row][6] == EMPTY:
            if not sq_attacked(row,5) and not sq_attacked(row,6):
                moves.append((row, 6, "castle_k"))
    # Queenside
    if castling_rights.get(color + "Q"):
        if board[row][3] == EMPTY and board[row][2] == EMPTY and board[row][1] == EMPTY:
            if not sq_attacked(row,3) and not sq_attacked(row,2):
                moves.append((row, 2, "castle_q"))
    return moves

def apply_castle(board, color, side):
    import copy
    nb = copy.deepcopy(board)
    row = 7 if color == W else 0
    if side == "k":
        nb[row][6] = color + "K"
        nb[row][5] = color + "R"
        nb[row][4] = EMPTY
        nb[row][7] = EMPTY
    else:
        nb[row][2] = color + "K"
        nb[row][3] = color + "R"
        nb[row][4] = EMPTY
        nb[row][0] = EMPTY
    return nb

# ── Input helpers ──────────────────────────────────────────────────────────────

def parse_sq(s):
    s = s.strip().lower()
    if len(s) != 2:
        return None
    c = ord(s[0]) - ord("a")
    r = int(s[1]) - 1
    if not in_bounds(r, c):
        return None
    return (r, c)

def banner(text, color_code):
    width = 50
    border = color_code + BOLD + "═" * width + RESET
    line = color_code + BOLD + "║  " + text.center(width - 4) + "  ║" + RESET
    print(border)
    print(line)
    print(border)

def loser_screen():
    clear()
    BG_RED = "\033[41m"
    W_ON_R = "\033[41m\033[97m\033[1m"
    lines = [
        "██╗   ██╗ ██████╗ ██╗   ██╗    ██╗      ██████╗ ███████╗███████╗",
        "╚██╗ ██╔╝██╔═══██╗██║   ██║    ██║     ██╔═══██╗██╔════╝██╔════╝",
        " ╚████╔╝ ██║   ██║██║   ██║    ██║     ██║   ██║███████╗█████╗  ",
        "  ╚██╔╝  ██║   ██║██║   ██║    ██║     ██║   ██║╚════██║██╔══╝  ",
        "   ██║   ╚██████╔╝╚██████╔╝    ███████╗╚██████╔╝███████║███████╗",
        "   ╚═╝    ╚═════╝  ╚═════╝     ╚══════╝ ╚═════╝ ╚══════╝╚══════╝",
    ]
    taunts = [
        "  💀  skill issue  💀",
        "  get absolutely rekt",
        "  maybe try tic-tac-toe?",
        "  your king has fallen, peasant",
        "  L + ratio + bad at chess",
    ]
    import random
    taunt = random.choice(taunts)
    width = 80

    # Flash the screen red a few times
    for _ in range(3):
        clear()
        print(BG_RED + " " * width * 20 + RESET)
        time.sleep(0.12)
        clear()
        time.sleep(0.08)

    clear()
    print(BG_RED + " " * width + RESET)
    print(BG_RED + " " * width + RESET)
    for line in lines:
        pad = max(0, (width - len(line)) // 2)
        print(W_ON_R + " " * pad + line + " " * (width - pad - len(line)) + RESET)
    print(BG_RED + " " * width + RESET)
    taunt_pad = max(0, (width - len(taunt)) // 2)
    print(W_ON_R + " " * taunt_pad + taunt + " " * (width - taunt_pad - len(taunt)) + RESET)
    print(BG_RED + " " * width + RESET)
    print(BG_RED + " " * width + RESET)
    print()

# ── Networking ─────────────────────────────────────────────────────────────────

class Connection:
    def __init__(self, sock):
        self.sock = sock
        self.buf  = b""

    def send(self, data: dict):
        raw = json.dumps(data).encode() + b"\n"
        self.sock.sendall(raw)

    def recv(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self):
        try: self.sock.close()
        except: pass

# ── Game loop ──────────────────────────────────────────────────────────────────

def game_loop(conn: Connection, my_color: str):
    board      = make_board()
    en_passant = None
    castling   = {"wK": True, "wQ": True, "bK": True, "bQ": True}
    turn       = W
    selected   = None
    valid      = []
    last_move  = []
    msg        = ""

    def status_line():
        check = " " + RED + BOLD + "(CHECK!)" + RESET if is_in_check(board, turn) else ""
        whose = (GREEN + "YOUR" if turn == my_color else YELLOW + "OPPONENT'S") + RESET
        return f"  Turn: {whose} ({('White' if turn==W else 'Black')}){check}  |  Enter square (e.g. e2) or 'resign'"

    render(board, my_color, msg=status_line())

    while True:
        # ── Opponent's turn ────────────────────────────────────────────────
        if turn != my_color:
            render(board, my_color, last_move=last_move,
                   msg=YELLOW + "  Waiting for opponent's move..." + RESET)
            try:
                data = conn.recv()
            except ConnectionError:
                render(board, my_color, msg=RED + "  Opponent disconnected." + RESET)
                input("  Press Enter to exit.")
                return

            if data["type"] == "resign":
                render(board, my_color, last_move=last_move)
                print()
                banner("OPPONENT RESIGNED — YOU WIN!", GREEN)
                input("\n  Press Enter to exit.")
                return

            if data["type"] == "move":
                fr,fc,tr,tc = data["from_r"],data["from_c"],data["to_r"],data["to_c"]
                promo = data.get("promotion","Q")
                board, en_passant = apply_move(board, fr, fc, tr, tc, en_passant, promo)
                last_move = [(fr,fc),(tr,tc)]

                # Update castling rights
                for col in [W, B]:
                    row_k = 7 if col == W else 0
                    if board[row_k][4] != col+"K":
                        castling[col+"K"] = False
                        castling[col+"Q"] = False
                    if board[row_k][7] != col+"R": castling[col+"K"] = False
                    if board[row_k][0] != col+"R": castling[col+"Q"] = False

            elif data["type"] == "castle":
                side = data["side"]
                board = apply_castle(board, turn, side)
                last_move = []
                castling[turn+"K"] = False
                castling[turn+"Q"] = False

            turn = W if turn == B else B

            # Check end conditions for my turn coming up
            if turn == my_color:
                if is_checkmate(board, my_color, en_passant):
                    loser_screen()
                    input("  Press Enter to exit.")
                    return
                if is_stalemate(board, my_color, en_passant):
                    render(board, my_color, last_move=last_move)
                    print()
                    banner("STALEMATE — IT'S A DRAW!", YELLOW)
                    input("\n  Press Enter to exit.")
                    return

            render(board, my_color, last_move=last_move, msg=status_line())
            continue

        # ── My turn ────────────────────────────────────────────────────────
        try:
            raw = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            conn.send({"type": "resign"})
            print("\n  You resigned.")
            return

        if raw == "resign":
            conn.send({"type": "resign"})
            loser_screen()
            input("  Press Enter to exit.")
            return

        # ── Castling shorthand ─────────────────────────────────────────────
        if raw in ("o-o", "0-0"):
            cms = castle_moves(board, my_color, castling)
            ks = [m for m in cms if m[2]=="castle_k"]
            if ks:
                board = apply_castle(board, my_color, "k")
                castling[my_color+"K"] = False
                castling[my_color+"Q"] = False
                conn.send({"type":"castle","side":"k"})
                last_move = []
                turn = W if turn == B else B
                if is_checkmate(board, turn, en_passant):
                    render(board, my_color)
                    print()
                    banner("CHECKMATE — OPPONENT LOSES! YOU WIN!", GREEN)
                    conn.send({"type":"gameover","result":"checkmate"})
                    input("\n  Press Enter to exit.")
                    return
                render(board, my_color, last_move=last_move, msg=status_line())
            else:
                msg = RED + "  Kingside castling not available." + RESET
                render(board, my_color, last_move=last_move, msg=msg)
            continue

        if raw in ("o-o-o", "0-0-0"):
            cms = castle_moves(board, my_color, castling)
            qs = [m for m in cms if m[2]=="castle_q"]
            if qs:
                board = apply_castle(board, my_color, "q")
                castling[my_color+"K"] = False
                castling[my_color+"Q"] = False
                conn.send({"type":"castle","side":"q"})
                last_move = []
                turn = W if turn == B else B
                if is_checkmate(board, turn, en_passant):
                    render(board, my_color)
                    print()
                    banner("CHECKMATE — OPPONENT LOSES! YOU WIN!", GREEN)
                    conn.send({"type":"gameover","result":"checkmate"})
                    input("\n  Press Enter to exit.")
                    return
                render(board, my_color, last_move=last_move, msg=status_line())
            else:
                msg = RED + "  Queenside castling not available." + RESET
                render(board, my_color, last_move=last_move, msg=msg)
            continue

        sq = parse_sq(raw)
        if sq is None:
            msg = RED + "  Invalid input. Enter a square like e2, or 'resign'." + RESET
            render(board, my_color, selected, valid, last_move=last_move, msg=msg)
            continue

        r, c = sq

        # ── Select a piece ─────────────────────────────────────────────────
        if selected is None:
            piece = board[r][c]
            if color_of(piece) != my_color:
                msg = RED + "  That's not your piece." + RESET
                render(board, my_color, last_move=last_move, msg=msg)
                continue
            valid = legal_moves(board, r, c, en_passant)
            # Add castle moves if king
            if piece[1] == "K":
                for cm in castle_moves(board, my_color, castling):
                    valid.append((cm[0], cm[1]))
            if not valid:
                msg = YELLOW + "  That piece has no legal moves." + RESET
                render(board, my_color, last_move=last_move, msg=msg)
                continue
            selected = (r, c)
            msg = CYAN + f"  Selected {raw}. Now pick a destination." + RESET
            render(board, my_color, selected, valid, last_move=last_move, msg=msg)
            continue

        # ── Deselect ───────────────────────────────────────────────────────
        if (r, c) == selected:
            selected = None; valid = []
            render(board, my_color, last_move=last_move, msg=status_line())
            continue

        # ── Move ───────────────────────────────────────────────────────────
        if (r, c) not in valid:
            # Maybe re-selecting another piece
            piece = board[r][c]
            if color_of(piece) == my_color:
                valid = legal_moves(board, r, c, en_passant)
                if piece[1] == "K":
                    for cm in castle_moves(board, my_color, castling):
                        valid.append((cm[0], cm[1]))
                selected = (r, c)
                msg = CYAN + f"  Selected {raw}. Now pick a destination." + RESET
                render(board, my_color, selected, valid, last_move=last_move, msg=msg)
            else:
                msg = RED + "  Invalid move. Pick a highlighted square." + RESET
                render(board, my_color, selected, valid, last_move=last_move, msg=msg)
            continue

        fr, fc = selected
        piece = board[fr][fc]

        # Check if this is a castle move
        if piece[1] == "K" and abs(fc - c) == 2:
            side = "k" if c > fc else "q"
            board = apply_castle(board, my_color, side)
            castling[my_color+"K"] = False
            castling[my_color+"Q"] = False
            conn.send({"type":"castle","side":side})
            last_move = [(fr,fc),(r,c)]
            selected = None; valid = []
            turn = W if turn == B else B
            if is_checkmate(board, turn, en_passant):
                render(board, my_color)
                print()
                banner("CHECKMATE — OPPONENT LOSES! YOU WIN!", GREEN)
                conn.send({"type":"gameover","result":"checkmate"})
                input("\n  Press Enter to exit.")
                return
            render(board, my_color, last_move=last_move, msg=status_line())
            continue

        # Pawn promotion
        promo = "Q"
        if piece[1] == "P" and (r == 0 or r == 7):
            render(board, my_color, selected, valid, last_move=last_move,
                   msg=CYAN + "  Promote to? (Q/R/B/N): " + RESET)
            try:
                choice = input("  > ").strip().upper()
                if choice not in ("Q","R","B","N"):
                    choice = "Q"
                promo = choice
            except:
                pass

        board, en_passant = apply_move(board, fr, fc, r, c, en_passant, promo)
        last_move = [(fr,fc),(r,c)]

        # Update castling rights
        for col in [W, B]:
            row_k = 7 if col == W else 0
            if board[row_k][4] != col+"K":
                castling[col+"K"] = False
                castling[col+"Q"] = False
            if board[row_k][7] != col+"R": castling[col+"K"] = False
            if board[row_k][0] != col+"R": castling[col+"Q"] = False

        conn.send({"type":"move","from_r":fr,"from_c":fc,"to_r":r,"to_c":c,"promotion":promo})

        selected = None; valid = []
        turn = W if turn == B else B

        # Check end conditions for opponent's coming turn
        if is_checkmate(board, turn, en_passant):
            render(board, my_color, last_move=last_move)
            print()
            banner("CHECKMATE — OPPONENT LOSES! YOU WIN!", GREEN)
            conn.send({"type":"gameover","result":"checkmate"})
            input("\n  Press Enter to exit.")
            return
        if is_stalemate(board, turn, en_passant):
            render(board, my_color, last_move=last_move)
            print()
            banner("STALEMATE — IT'S A DRAW!", YELLOW)
            conn.send({"type":"gameover","result":"stalemate"})
            input("\n  Press Enter to exit.")
            return

        render(board, my_color, last_move=last_move, msg=status_line())

# ── Split-screen local rendering ──────────────────────────────────────────────

ANSI_ESC = "\033["

def strip_ansi(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def board_rows(board, flip=False, selected=None, valid_moves=None, last_move=None):
    """Return list of (raw_str, visible_str) pairs for each board row including labels.
    flip=True puts rank 8 at the bottom (Black's perspective)."""
    valid_set = set(valid_moves) if valid_moves else set()
    last_set  = set(last_move)   if last_move   else set()
    rows = range(8) if flip else range(7, -1, -1)   # flip: rank 1 top, rank 8 bottom
    cols = range(8)                                  # always a-h left to right

    lines = []
    col_label = "   " + "  ".join(chr(ord("a") + c) for c in cols) + "  "
    lines.append((BOLD + CYAN + col_label + RESET, col_label))

    for r in rows:
        rank_label = str(r + 1)
        row_str = BOLD + CYAN + rank_label + " " + RESET
        for c in cols:
            piece = board[r][c]
            is_light = (r + c) % 2 == 0
            if selected and (r, c) == selected:
                bg = BG_SEL
            elif (r, c) in valid_set:
                bg = BG_MOVE
            elif (r, c) in last_set:
                bg = BG_SEL
            elif is_light:
                bg = BG_LIGHT
            else:
                bg = BG_DARK
            symbol = PIECES.get(piece, "?")
            row_str += bg + " " + symbol + " " + RESET
        row_str += BOLD + CYAN + " " + rank_label + RESET
        lines.append((row_str, strip_ansi(row_str)))

    lines.append((BOLD + CYAN + col_label + RESET, col_label))
    return lines

def render_split(board, turn, selected=None, valid_moves=None, last_move=None, msg=""):
    """Render both boards side by side — White's view left, Black's view right."""
    clear()
    GAP = "      "
    SEP = BOLD + "  ║  " + RESET

    w_rows = board_rows(board, flip=False, selected=selected if turn == W else None,
                        valid_moves=valid_moves if turn == W else None, last_move=last_move)
    b_rows = board_rows(board, flip=True,  selected=selected if turn == B else None,
                        valid_moves=valid_moves if turn == B else None, last_move=last_move)

    w_label = (GREEN if turn == W else WHITE) + BOLD + "  ── White ──" + RESET
    b_label = (GREEN if turn == B else WHITE) + BOLD + "  ── Black ──" + RESET
    col_w = 30
    print(w_label.ljust(col_w + 20) + GAP + b_label)

    for (wr, wv), (br, bv) in zip(w_rows, b_rows):
        pad = col_w - len(wv)
        print(wr + " " * max(0, pad) + SEP + br)

    print()
    if msg:
        print(msg)

# ── Local (same-PC) game loop ──────────────────────────────────────────────────

def local_game():
    board      = make_board()
    en_passant = None
    castling   = {"wK": True, "wQ": True, "bK": True, "bQ": True}
    turn       = W
    selected   = None
    valid      = []
    last_move  = []
    msg        = ""

    def status():
        who   = (GREEN + BOLD + "WHITE" if turn == W else CYAN + BOLD + "BLACK") + RESET
        check = " " + RED + BOLD + "(CHECK!)" + RESET if is_in_check(board, turn) else ""
        return f"  {who}'s turn{check}  —  e.g. 'e2 e4' or 'e2' then 'e4', or 'resign'"

    render_split(board, turn, msg=status())

    def do_move(fr, fc, tr, tc):
        """Execute a validated move. Returns 'checkmate', 'stalemate', or None."""
        nonlocal board, en_passant, turn, selected, valid, last_move

        piece = board[fr][fc]

        # Castle via king moving two squares
        if piece[1] == "K" and abs(fc - tc) == 2:
            side = "k" if tc > fc else "q"
            board = apply_castle(board, turn, side)
            castling[turn+"K"] = False; castling[turn+"Q"] = False
            last_move = [(fr,fc),(tr,tc)]; selected = None; valid = []
            turn = B if turn == W else W
            if is_checkmate(board, turn, en_passant): return "checkmate"
            return None

        # Promotion
        promo = "Q"
        if piece[1] == "P" and (tr == 0 or tr == 7):
            render_split(board, turn, None, None, last_move,
                         CYAN + "  Promote to? (Q/R/B/N): " + RESET)
            try:
                choice = input("  > ").strip().upper()
                promo = choice if choice in ("Q","R","B","N") else "Q"
            except: pass

        board, en_passant = apply_move(board, fr, fc, tr, tc, en_passant, promo)
        last_move = [(fr,fc),(tr,tc)]

        for col in [W, B]:
            row_k = 7 if col == W else 0
            if board[row_k][4] != col+"K":
                castling[col+"K"] = False; castling[col+"Q"] = False
            if board[row_k][7] != col+"R": castling[col+"K"] = False
            if board[row_k][0] != col+"R": castling[col+"Q"] = False

        selected = None; valid = []
        turn = B if turn == W else W
        if is_checkmate(board, turn, en_passant): return "checkmate"
        if is_stalemate(board, turn, en_passant): return "stalemate"
        return None

    while True:
        try:
            raw = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Quit.")
            return

        if raw == "resign":
            loser_screen()
            input("  Press Enter to exit.")
            return

        # Castling shorthand
        if raw in ("o-o", "0-0"):
            cms = castle_moves(board, turn, castling)
            ks = [m for m in cms if m[2] == "castle_k"]
            if ks:
                board = apply_castle(board, turn, "k")
                castling[turn+"K"] = False; castling[turn+"Q"] = False
                last_move = []; turn = B if turn == W else W
                if is_checkmate(board, turn, en_passant):
                    render_split(board, turn, last_move=last_move)
                    loser_screen(); input("  Press Enter to exit."); return
                render_split(board, turn, last_move=last_move, msg=status())
            else:
                render_split(board, turn, selected, valid, last_move,
                             RED + "  Kingside castling not available." + RESET)
            continue

        if raw in ("o-o-o", "0-0-0"):
            cms = castle_moves(board, turn, castling)
            qs = [m for m in cms if m[2] == "castle_q"]
            if qs:
                board = apply_castle(board, turn, "q")
                castling[turn+"K"] = False; castling[turn+"Q"] = False
                last_move = []; turn = B if turn == W else W
                if is_checkmate(board, turn, en_passant):
                    render_split(board, turn, last_move=last_move)
                    loser_screen(); input("  Press Enter to exit."); return
                render_split(board, turn, last_move=last_move, msg=status())
            else:
                render_split(board, turn, selected, valid, last_move,
                             RED + "  Queenside castling not available." + RESET)
            continue

        # "e2 e4" — two squares at once
        parts = raw.split()
        if len(parts) == 2:
            fsq = parse_sq(parts[0]); tsq = parse_sq(parts[1])
            if not fsq or not tsq:
                render_split(board, turn, selected, valid, last_move,
                             RED + "  Invalid squares. Try: e2 e4" + RESET)
                continue
            fr, fc = fsq; tr, tc = tsq
            piece = board[fr][fc]
            if color_of(piece) != turn:
                render_split(board, turn, last_move=last_move,
                             msg=RED + "  That's not your piece." + RESET)
                continue
            lm = legal_moves(board, fr, fc, en_passant)
            if piece[1] == "K":
                for cm in castle_moves(board, turn, castling):
                    lm.append((cm[0], cm[1]))
            if (tr, tc) not in lm:
                render_split(board, turn, last_move=last_move,
                             msg=RED + f"  Can't move {parts[0]} to {parts[1]}." + RESET)
                continue
            result = do_move(fr, fc, tr, tc)
            if result == "checkmate":
                render_split(board, turn, last_move=last_move)
                loser_screen(); input("  Press Enter to exit."); return
            if result == "stalemate":
                render_split(board, turn, last_move=last_move)
                banner("STALEMATE — IT'S A DRAW!", YELLOW)
                input("\n  Press Enter to exit."); return
            render_split(board, turn, last_move=last_move, msg=status())
            continue

        # Single square — select or move
        sq = parse_sq(raw)
        if sq is None:
            render_split(board, turn, selected, valid, last_move,
                         RED + "  Invalid input. Try: e2 e4 or just e2" + RESET)
            continue

        r, c = sq

        if selected is None:
            piece = board[r][c]
            if color_of(piece) != turn:
                render_split(board, turn, last_move=last_move,
                             msg=RED + "  That's not your piece." + RESET)
                continue
            valid = legal_moves(board, r, c, en_passant)
            if piece[1] == "K":
                for cm in castle_moves(board, turn, castling):
                    valid.append((cm[0], cm[1]))
            if not valid:
                render_split(board, turn, last_move=last_move,
                             msg=YELLOW + "  That piece has no legal moves." + RESET)
                continue
            selected = (r, c)
            render_split(board, turn, selected, valid, last_move,
                         CYAN + f"  Selected {raw}. Now pick a destination." + RESET)
            continue

        if (r, c) == selected:
            selected = None; valid = []
            render_split(board, turn, last_move=last_move, msg=status())
            continue

        if (r, c) not in valid:
            piece = board[r][c]
            if color_of(piece) == turn:
                valid = legal_moves(board, r, c, en_passant)
                if piece[1] == "K":
                    for cm in castle_moves(board, turn, castling):
                        valid.append((cm[0], cm[1]))
                selected = (r, c)
                render_split(board, turn, selected, valid, last_move,
                             CYAN + f"  Selected {raw}. Now pick a destination." + RESET)
            else:
                render_split(board, turn, selected, valid, last_move,
                             RED + "  Invalid move. Pick a highlighted square." + RESET)
            continue

        fr, fc = selected
        result = do_move(fr, fc, r, c)
        if result == "checkmate":
            render_split(board, turn, last_move=last_move)
            loser_screen(); input("  Press Enter to exit."); return
        if result == "stalemate":
            render_split(board, turn, last_move=last_move)
            banner("STALEMATE — IT'S A DRAW!", YELLOW)
            input("\n  Press Enter to exit."); return
        render_split(board, turn, last_move=last_move, msg=status())

# ── Entry point ────────────────────────────────────────────────────────────────

def host_game(port):
    print(BOLD + GREEN + f"\n  Hosting on port {port}..." + RESET)

    # Show local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"

    print(f"  Your IP: {BOLD}{CYAN}{local_ip}{RESET}")
    print(f"  Tell your opponent to run:  {BOLD}python chess.py join {local_ip} {port}{RESET}\n")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print("  Waiting for opponent to connect...")
    client_sock, addr = srv.accept()
    srv.close()
    print(f"  {GREEN}Opponent connected from {addr[0]}!{RESET}\n")

    conn = Connection(client_sock)
    # Host is White
    conn.send({"type": "color", "color": B})
    time.sleep(0.1)
    game_loop(conn, W)

def join_game(host_ip, port):
    print(BOLD + CYAN + f"\n  Connecting to {host_ip}:{port}..." + RESET)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host_ip, port))
    except Exception as e:
        print(RED + f"  Could not connect: {e}" + RESET)
        sys.exit(1)

    conn = Connection(sock)
    data = conn.recv()
    if data["type"] != "color":
        print(RED + "  Unexpected handshake." + RESET)
        sys.exit(1)
    my_color = data["color"]
    print(f"  {GREEN}Connected! You are {'White' if my_color==W else 'Black'}.{RESET}\n")
    time.sleep(0.3)
    game_loop(conn, my_color)

def print_help():
    print(f"""
{BOLD}{CYAN}  ♔  Terminal Chess  ♚{RESET}

  {BOLD}Usage:{RESET}
    Same PC (split-screen):  {GREEN}python chess.py local{RESET}
    Host a network game:     {GREEN}python chess.py host [port]{RESET}
    Join a network game:     {GREEN}python chess.py join <ip> [port]{RESET}

  {BOLD}In-game controls:{RESET}
    Type a square (e.g. {CYAN}e2{RESET}) to select, then another to move.
    Highlighted squares show legal moves.
    Type {CYAN}o-o{RESET} or {CYAN}o-o-o{RESET} to castle (kingside / queenside).
    Type {CYAN}resign{RESET} to resign.

  {BOLD}Default port:{RESET} {DEFAULT_PORT}
""")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "local":
        local_game()
    elif cmd == "host":
        port = int(args[1]) if len(args) > 1 else DEFAULT_PORT
        host_game(port)
    elif cmd == "join":
        if len(args) < 2:
            print(RED + "  Usage: python chess.py join <ip> [port]" + RESET)
            sys.exit(1)
        ip   = args[1]
        port = int(args[2]) if len(args) > 2 else DEFAULT_PORT
        join_game(ip, port)
    else:
        print_help()
        sys.exit(1)
