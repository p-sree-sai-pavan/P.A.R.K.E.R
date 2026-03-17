# P.A.R.K.E.R: Memory Language Project

## Overview
P.A.R.K.E.R is an advanced memory language project designed to simulate memory, learning, and communication processes. The project is modular, with components for memory storage, processing, and interaction.

## Features
- Modular architecture: brain, ears, mouth, short-term and long-term memory modules
- Docker support for easy deployment
- Jupyter notebook for experimentation
- Python-based, easy to extend

## Project Structure
- `brain.py`: Core logic for memory processing
- `ears.py`: Input and perception module
- `mouth.py`: Output and communication module
- `short.py`: Short-term memory implementation
- `long.py`: Long-term memory implementation
- `main.py`: Main entry point for running the project
- `main.ipynb`: Jupyter notebook for interactive exploration
- `docker-compose.yaml`: Docker configuration for deployment
- `memory.json`: Data storage for memory

## Getting Started
1. **Clone the repository:**
   ```bash
   git clone https://github.com/p-sree-sai-pavan/P.A.R.K.E.R.git
   cd P.A.R.K.E.R
   ```
2. **Install dependencies:**
   - Ensure you have Python 3.8+ installed
   - (Optional) Use Docker for containerized setup
3. **Run the project:**
   ```bash
   python main.py
   ```
4. **Explore with Jupyter Notebook:**
   ```bash
   jupyter notebook main.ipynb
   ```

## Docker Usage
To run the project using Docker Compose:
```bash
docker-compose up --build
```

## Contributing
Contributions are welcome! Please open issues or pull requests for improvements.

## License
This project is licensed under the MIT License.
