(defun yas//decl-name ()
  "Heuristically returns declared name via regex:"
  (yas-substr yas-text ".*[^[:alnum:]_]\\([[:alnum:]_]*\\)" 1))
