# miniGPTKB
This is the repository containing code and data of the miniGPTKB experiments.

To cite our work:

**Giordano, L., & Razniewski, S. (2026). Foundations of LLM Knowledge Materialization: Termination, Reproducibility, Robustness. In _Findings of EACL 2026_**

https://arxiv.org/pdf/2510.06780

## GUI

The `GUI/` folder contains all necessary components to run the GUI application that triggers `local_kbc.py`. It consists of two folders and one main file:

1. `backend/`
   * `runner.py`: Contains a function that simply triggers `main()` in `local_kbc.py`.
2. `UI/`
   * `window.py`: Contains the `QtLogHandler` class for displaying logs and the `MainWindow` class, which defines the UI layout and functionality.
3. `main.py`
   * Starts the GUI application.

### Arguments
1. **Directory**: Lets the user browse and select a directory, starting from the home directory.
2. **LLM URL**: Automatically set to the Scads.AI URL, but can also be entered manually.
3. **Model Input**: A selection of five models available at Scads.AI. A custom model name can also be entered manually.
4. **Topic**: Editable field for the topic. *"Ancient Babylon"* is displayed as an example.
5. **Seed Entity**: Starting entity for the knowledge base expansion. *"Hammurabi"* is displayed as an example.
6. **Termination Options**: Optional stopping criteria. Either **Min Entities** (minimum number of entities to process) or **Runtime** (soft time limit).
7. **Desired Number of Triples**: Range for the number of triples requested in the model prompt.
