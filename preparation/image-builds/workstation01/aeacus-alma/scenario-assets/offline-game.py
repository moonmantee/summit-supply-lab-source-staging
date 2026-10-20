#!/usr/bin/env python3
# SUMMIT-TRAINING-OFFLINE-GAME
import random
number=random.randint(1,10)
try:
    guess=int(input("Guess a number from 1 to 10: "))
    print("Correct!" if guess==number else "The answer was %d" % number)
except (ValueError,EOFError):
    print("Game ended.")
