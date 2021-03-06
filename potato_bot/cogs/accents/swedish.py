import re
import random

from typing import Optional

from .accent import Accent


def bork(m: re.Match) -> Optional[str]:
    if random.random() > 1 / 3:
        return

    return f" Bork{', bork' * random.randint(0, 2)}!"


# https://github.com/unitystation/unitystation/blob/cf3bfff6563f0b3d47752e19021ab145ae318736/UnityProject/Assets/Resources/ScriptableObjects/Speech/Swedish.asset
class Swedish(Accent):
    REPLACEMENTS = {
        r"w": "v",
        r"j": "y",
        r"a": (
            "å",
            "ä",
            "æ",
            "a",
        ),
        r"bo": "bjo",
        r"o": (
            "ö",
            "ø",
            "o",
        ),
        Accent.MESSAGE_END: bork,
    }
