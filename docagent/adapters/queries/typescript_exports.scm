;; Captures every `export ...` statement so the adapter's `extract_exports`
;; can distinguish barrel files (all re-exports) from original-definition
;; modules. Children are walked in Python — tree-sitter-typescript's
;; export_statement encodes too many shapes (export *, export { x } [from],
;; export type { ... }, export default <decl>, export <decl>) for a single
;; structured pattern to capture without ambiguity.

(export_statement) @export.stmt
