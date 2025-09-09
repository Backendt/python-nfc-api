from smartcard.CardType import ATRCardType, CardType
from typing import Final

class Tag:
    atr: CardType
    bytes_per_page: int
    memory_page_start: int
    memory_page_max: int

    def __init__(self, atr: list[int], bytes_per_page: int, memory_page_start: int, memory_page_max: int):
        self.atr = ATRCardType(atr)
        self.bytes_per_page = bytes_per_page
        self.memory_page_start = memory_page_start
        self.memory_page_max = memory_page_max

# The values comes from: https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf 
NTAG216: Final[Tag] = Tag([59, 143, 128, 1, 128, 79, 12, 160, 0, 0, 3, 6, 3, 0, 3, 0, 0, 0, 0, 104], 4, 4, 226)
