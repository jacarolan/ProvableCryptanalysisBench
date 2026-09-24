import GGM.Certificate

namespace Submission
open GGM

-- A constant answer and zero-query bound cannot solve random discrete log.
-- This fixture must fail typechecking, not merely a string scan.
def certificate : Certificate where
  seeds := 1
  seeds_pos := by decide
  attack := fun _ _ => .ret 0
  bound := .constant 0
  correct := by intro p hp s x; rfl
  expected_le := by intro p hp; rfl

end Submission
