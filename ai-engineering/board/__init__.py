"""Layer 2 - Executive Product Board (Britsync AIED).

The highest decision-making authority before development begins. Nine
executive members review every request from six perspectives (business,
customer, UX, engineering, growth, risk) plus strategy and innovation, then
the Executive Review Chair produces a weighted scorecard and a Decision
Package handed to the development agents.
"""

from board.engine import ExecutiveProductBoard
from board.models import BoardMemberVerdict, BoardReview, ScorecardEntry
from board.prompts import BOARD_MEMBERS, BOARD_ORDER, SCORE_MEMBERS

__all__ = [
    "ExecutiveProductBoard",
    "BoardMemberVerdict",
    "BoardReview",
    "ScorecardEntry",
    "BOARD_MEMBERS",
    "BOARD_ORDER",
    "SCORE_MEMBERS",
]
