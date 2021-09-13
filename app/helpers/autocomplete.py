from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataclasses import dataclass as autocomplete
else:
    def autocomplete(model):
        return model
