"""骰子规则。和皮肤分开：皮肤只管怎么画，点数只由这里决定。"""
import random


class D6:
    faces = 6

    def roll(self, rng=random):
        return rng.randint(1, self.faces)
