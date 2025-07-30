;; Guix manifest for bibliography management system

(specifications->manifest
 '("git"
   "python"
   "python-bibtexparser-1" ; BibTeX parsing and manipulation (v1.4)
   "python-pytest"       ; Testing framework
   "python-pyyaml"       ; YAML configuration parsing
   "python-click"        ; CLI framework
   "python-ruff"         ; Python linter and formatter
   "node-pyright"        ; Type checking
   "python-lsp-server"   ; LSP support for editors
   "ripgrep"             ; Fast file searching
   "coreutils"))