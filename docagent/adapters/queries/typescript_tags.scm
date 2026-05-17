;; Symbol-definition patterns for the TypeScript/JavaScript adapter.
;;
;; Adapted from upstream tree-sitter `tags.scm` files
;; (https://github.com/tree-sitter/tree-sitter-typescript,
;;  https://github.com/tree-sitter/tree-sitter-javascript), both MIT-licensed.
;; Reference-capture clauses and JSDoc-association predicates from upstream are
;; dropped — v1 of this adapter doesn't yet consume references or splice
;; existing doc comments. Constructors and private (`#`-prefixed or named
;; ``constructor``) members are filtered post-query in `extract_symbols`.
;;
;; Captures: every def-node uses ``@def.<kind>`` so the adapter can map node
;; type → SymbolKind from one source. ``@name`` is always the leaf identifier.

;; Functions
(function_declaration
  name: (identifier) @name) @def.function

(generator_function_declaration
  name: (identifier) @name) @def.function

(function_signature
  name: (identifier) @name) @def.function

;; Arrow / function-expression assigned to a binding at module or container scope.
;; (The variable_declarator span covers `name = value`.)
(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)]) @def.function)

(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)]) @def.function)

;; CommonJS / object-shape function bindings:
;;   module.exports.foo = () => {}
;;   exports.foo       = () => {}
;;   foo               = () => {}            (rare, but matches upstream JS)
(assignment_expression
  left: (member_expression
    property: (property_identifier) @name)
  right: [(arrow_function) (function_expression)]) @def.function

(assignment_expression
  left: (identifier) @name
  right: [(arrow_function) (function_expression)]) @def.function

;; Classes
(class_declaration
  name: (type_identifier) @name) @def.class

(abstract_class_declaration
  name: (type_identifier) @name) @def.class

;; Methods (concrete, abstract, interface signature)
(method_definition
  name: (property_identifier) @name) @def.method

(abstract_method_signature
  name: (property_identifier) @name) @def.method

(method_signature
  name: (property_identifier) @name) @def.method

;; Interfaces
(interface_declaration
  name: (type_identifier) @name) @def.interface

;; Type aliases
(type_alias_declaration
  name: (type_identifier) @name) @def.type_alias

;; Enums
(enum_declaration
  name: (identifier) @name) @def.enum

;; TypeScript namespaces (`namespace Foo {}` parses as internal_module)
;; and `module Foo {}` when Foo is an identifier (not an ambient string name).
(internal_module
  name: (identifier) @name) @def.module

(module
  name: (identifier) @name) @def.module

;; JSDoc candidates — top-level block comments. The adapter filters `/**` vs
;; `/*` in Python (runtime portability across tree-sitter binding versions
;; than #match? predicates) and pairs each `/**` block with the
;; immediately-following @def.<kind> node.
(comment) @jsdoc.candidate
