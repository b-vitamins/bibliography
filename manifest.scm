;; Guix manifest for bibliography management system

(specifications->manifest
 '("git"
   "python"
   "python-bibtexparser-1" ; BibTeX parsing and manipulation (v1.4)
   "python-pytest"       ; Testing framework
   "python-pytest-cov"   ; Code coverage reporting
   "python-pyyaml"       ; YAML configuration parsing
   "python-click"        ; CLI framework
   "python-rich"         ; Rich terminal output and formatting
   "python-ruff"         ; Python linter and formatter
   "node-pyright"        ; Type checking
   "python-lsp-server"   ; LSP support for editors
   "ripgrep"             ; Fast file searching
   "coreutils"))