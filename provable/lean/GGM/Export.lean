import GGM.Certificate
import Lean

namespace GGM

def Bound.toJson : Bound → Lean.Json
  | .constant k => Lean.Json.mkObj [("op", "constant"), ("value", Lean.toJson k)]
  | .order => Lean.Json.mkObj [("op", "order")]
  | .sqrtOrder => Lean.Json.mkObj [("op", "sqrtOrder")]
  | .add a b => Lean.Json.mkObj [("op", "add"), ("a", a.toJson), ("b", b.toJson)]
  | .mul a b => Lean.Json.mkObj [("op", "mul"), ("a", a.toJson), ("b", b.toJson)]
  | .div a k => Lean.Json.mkObj [("op", "div"), ("a", a.toJson), ("denominator", Lean.toJson k)]

/-- Exports only the bound AST and seed count, never executes the attack. -/
def exportCertificate (c : Certificate) : String :=
  (Lean.Json.mkObj [("schema_version", Lean.toJson (1 : Nat)), ("seeds", Lean.toJson c.seeds),
    ("bound", c.bound.toJson)]).compress

end GGM
