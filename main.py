# Generate a little round to roles sheet for the play draft gamble.


import random
from enum import IntEnum
from typing import Type, List


class Role(IntEnum):
    DRAFTER = 0
    GAMBLER = 1
    TAPPER = 2


ROLE_SIZES = {Role.DRAFTER: 2, Role.GAMBLER: 8, Role.TAPPER: 10}

# The code has not been checked to work with other values of NUM_PLAYERS, and especially makes an assumption
# that NUM_ROUNDS divides NUM_PLAYERS evenly.
NUM_PLAYERS = sum(ROLE_SIZES.values())
NUM_ROUNDS = 10


PlayerIndex: Type = int
RoundIndex: Type = int


class RoleMask:

    def __init__(self):
        self.has_role_mask = 0

    def take_role_for_round(self, round_id: RoundIndex):
        assert not self.has_role_for_round(round_id)
        self.has_role_mask |= (1 << round_id)

    def has_role_for_round(self, round_id: RoundIndex) -> bool:
        return self.has_role_mask & (1 << round_id) != 0

    def lose_role_for_round(self, round_id: RoundIndex):
        assert self.has_role_for_round(round_id)
        self.has_role_mask -= (1 << round_id)

    def active_rounds(self) -> List[RoundIndex]:
        ret = []
        for round_id in range(NUM_ROUNDS):
            if self.has_role_mask & (1 << round_id):
                ret.append(round_id)
        return ret


# This implementation would get way simpler if we replace has_role_masks with a list[Role].
class PlayerRolesAllocation:
    def __init__(self):
        self.has_role_masks = [RoleMask() for _ in Role]

    def take_role_for_round(self, role: Role, round_id: RoundIndex):
        self.has_role_masks[role].take_role_for_round(round_id)

    def lose_role_for_round(self, role: Role, round_id: RoundIndex):
        self.has_role_masks[role].lose_role_for_round(round_id)

    def swap_role_for_round(self, round_id: RoundIndex, role: Role, other_role: Role):
        self.has_role_masks[role].lose_role_for_round(round_id)
        self.has_role_masks[other_role].take_role_for_round(round_id)

    def get_role_for_round(self, round_id: RoundIndex) -> Role:
        for role in Role:
            if self.has_role_masks[role].has_role_for_round(round_id):
                return role
        assert False, "couldn't find role?"


EntireAllocation: Type = List[PlayerRolesAllocation]  # indexed by PlayerIndex

players = ["Rob", "Nick M", "Brian", "Ryan P", "Woody", "Wyatt", "Mario", "Tyler", "John Ryan", "Jimmy J Leong", "TayTay", "Sam B", "TJ", "Dan", "Marian", "Alec", "Daph", "Keith", "Joyce", "Coppola"]
assert(len(players) == NUM_PLAYERS)


def main():
    allocation: EntireAllocation = list()
    for player_index in range(NUM_PLAYERS):
        allocation.append(PlayerRolesAllocation())

    role_stride = NUM_PLAYERS / NUM_ROUNDS
    template_roles: List[Role] = list()
    for role in Role:
        for _ in range(ROLE_SIZES[role]):
            template_roles.append(role)

    for round_id in range(NUM_ROUNDS):
        template_offset: PlayerIndex = int(round_id * role_stride)
        for player_index in range(NUM_PLAYERS):
            allocated_role: Role = template_roles[(template_offset + player_index) % NUM_PLAYERS]
            allocation[player_index].take_role_for_round(allocated_role, round_id)
    swap_counter = 0
    for _ in range(10000):
        p1: PlayerIndex = random.randint(0, NUM_PLAYERS - 1)
        p2: PlayerIndex = random.randint(0, NUM_PLAYERS - 1)
        while p2 == p1:
            p2 = random.randint(0, NUM_PLAYERS - 1)
        # Find a pair of rounds (round, other_round) where p1 has role r1 in round, r2 in other_round and
        #                                    p2 has role r2 in round, r1 in other_round

        round_id = random.randint(0, NUM_ROUNDS - 1)
        r1 = allocation[p1].get_role_for_round(round_id)
        r2 = allocation[p2].get_role_for_round(round_id)

        if r1 != r2:
            round_offset = random.randint(0, NUM_ROUNDS - 1)
            for round_step in range(1, NUM_ROUNDS):
                other_round = (round_offset + round_step) % NUM_ROUNDS
                if (allocation[p1].get_role_for_round(other_round) == r2 and allocation[p2].get_role_for_round(other_round) == r1):

                    allocation[p1].swap_role_for_round(round_id, r1, r2)
                    allocation[p2].swap_role_for_round(round_id, r2, r1)

                    allocation[p1].swap_role_for_round(other_round, r2, r1)
                    allocation[p2].swap_role_for_round(other_round, r1, r2)

                    swap_counter += 1
                    # print(f"Found swap from players {p1} and {p2} at rounds {round} and {other_round} with roles {r1} and {r2}")
                    # assert allocation[p1][Role.DRAFTER]
                    break
            else:
                pass
                # print("Couldn't find viable swap")

    # It could be worthwhile to also try to optimize these conditions:
    # 1. Players tend to mix, so that everyone plays in the same round roughly an equal number of times
    # 2. Players don't tend to have to wait long between rounds that they play.
    # 3. Players get a roughly even chance at playing in late rounds.
    for round_id in range(NUM_ROUNDS):
        for role in Role:
            for player_index in range(NUM_PLAYERS):
                if allocation[player_index].get_role_for_round(round_id) == role:

                    print(f'{players[player_index]},', end='')
        print()


if __name__ == '__main__':
    main()

