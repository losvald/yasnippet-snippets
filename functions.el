;; Functions called from snippets - must be interactive
;; Defined here to avoid dependency on init.el
;; Usage:
;;   (load <path_to_this_file>)  ; from init.el / .emacs

(defun file-dirname (filepath)
  "Returns the last path component of a file's directory.
E.g., \"ab/dir/file\" => \"dir\"."
  (interactive "P")
  (file-name-nondirectory (directory-file-name (file-name-directory filepath))))

(defun camelize (s)
  "Convert under_score string S to CamelCase string."
  (interactive "P")
  (mapconcat 'identity (mapcar
			'(lambda (word) (if (or (> (length word) 2)
						(member word '("go" "or")))
					    (capitalize (downcase word))
					  (upcase word)))
			(split-string s "_")) ""))
