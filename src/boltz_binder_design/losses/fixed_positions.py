# Generic loss functions for fixing positions in a binder sequence
# Note: if you're finetuning an existing binder you might want to
#  - If you're using Boltz: use a binder sequence (instead of all "X"'s) to generate features
#  - If using AF2: set the wildtype complex as the initial guess (maybe, this hasn't been tested)
#  - Add additional loss functions to constrain the design to be close to the wildtype (if you have a complex):
#    - ProteinMPNN inverse folding for the complex
#    - Some kind of distance metric on the predicted complex structure, e.g. DistogramCE
#
import jax.numpy as jnp
import numpy as np
from jaxtyping import Array, Bool, Float, Int
import jax

from ..common import TOKENS, LinearCombination, LossTerm


class SetPositions(LossTerm):
    """Precomposes loss functional with function that maps a soft sequence of ONLY VARIABLE positions to a full binder sequence to eliminate constraints/penalties.
    WARNING: Be sure to call `sequence` *after* optimization, e.g. `loss.sequence(jax.nn.softmax(logits))`."""

    wildtype: Int[Array, "N"]
    variable_positions: Int[Array, "M"]
    loss: LossTerm | LinearCombination

    def __call__(self, seq: Float[Array, "M 20"], *, key):
        assert seq.shape == (len(self.variable_positions), len(TOKENS))
        return self.loss(self.sequence(seq), key=key)

    def sequence(self, seq: Float[Array, "M 20"]):
        return (
            jax.nn.one_hot(self.wildtype, len(TOKENS))
            .at[self.variable_positions]
            .set(seq)
        )

    @staticmethod
    def from_sequence(wildtype: str, loss: LossTerm | LinearCombination):
        """Fix standard amino acids but allow variability at positions with 'X'"""
        wildtype_tokens = jnp.array([TOKENS.index(AA) for AA in wildtype])
        variable_positions = jnp.array(
            [i for i, AA in enumerate(wildtype) if AA == "X"]
        )
        return SetPositions(wildtype_tokens, variable_positions, loss)


class FixedPositionsPenalty(LossTerm):
    """Penalizes deviation from target at fixed positions using L2^2 loss. Might make optimization more difficult compared to `SetPositions` below, but is simpler"""

    position_mask: Bool[Array, "N"]
    target: Float[Array, "N 20"]

    def __call__(self, seq: Float[Array, "N 20"], *, key):
        r = (((seq - self.target) ** 2).sum(-1) * self.position_mask).sum()
        return r, {"fixed_position_penalty": r}

    @staticmethod
    def from_residues(sequence_length: int, positions_and_AAs: list[tuple[int, str]]):
        position_mask = np.zeros(sequence_length, dtype=bool)
        target = np.zeros((sequence_length, len(TOKENS)))
        for idx, AA in positions_and_AAs:
            position_mask[idx] = True
            target[idx, TOKENS.index(AA)] = 1.0

        return FixedPositionsPenalty(jnp.array(position_mask), jnp.array(target))
