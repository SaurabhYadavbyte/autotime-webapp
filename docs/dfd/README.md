# AutoTime Data Flow Diagrams

This folder contains the deliberately simplified DFDs for AutoTime:

- `level-0-context`: the whole application is represented as one process.
- `level-1-main-processes`: the application is decomposed into four main processes.

Level 2 is intentionally omitted because the requested scope is the main AutoTime flow. The Level 0 and Level 1 diagrams are balanced: the Admin, Teacher, and Student inputs/outputs at the context boundary are preserved in the Level 1 decomposition.

The diagrams follow the main DFD constraints:

- external entities do not exchange data directly;
- data stores appear only after Level 0;
- every data-store flow passes through a process;
- flows are labelled with the data being transferred;
- each process has at least one input and one output.

Editable Graphviz `.dot` sources and rendered `.svg`/`.png` files are included. Run `node build.cjs` with `@viz-js/viz` and `sharp` available to rebuild the rendered files.
