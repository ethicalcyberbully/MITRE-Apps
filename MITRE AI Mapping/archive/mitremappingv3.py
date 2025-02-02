import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from queue import Queue, Empty

def install_and_import_packages():
    """
    Ensures necessary packages are installed, using the --user flag to avoid permission issues.
    """
    required_packages = ["sentence-transformers", "attackcti", "numpy", "pydantic"]
    try:
        # Check if packages are already installed
        installed_packages = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']).decode('utf-8').lower()
        missing_packages = [pkg for pkg in required_packages if pkg.lower() not in installed_packages]
        
        # Install any missing packages
        for package in missing_packages:
            print(f"{package} not found. Installing for user...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--user"])
    except subprocess.CalledProcessError as e:
        print(f"Failed to install required packages: {e}")
        sys.exit(1)

    # Import installed packages globally
    global SentenceTransformer, util, attack_client, np
    from sentence_transformers import SentenceTransformer, util
    from attackcti import attack_client
    import numpy as np

# Import necessary packages
install_and_import_packages()

# Initialize the NLP model and MITRE ATT&CK client only once to avoid re-initialization
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
lift = attack_client()

def find_similar_techniques(sentence, progress_callback, result_queue):
    """
    Finds similar MITRE ATT&CK techniques based on the input sentence. Updates progress and posts results to the queue.
    """
    try:
        sentence_embedding = model.encode(sentence, convert_to_tensor=True)
        progress_callback(20)
    except Exception as e:
        messagebox.showerror("Error", f"Error encoding sentence: {e}")
        return

    try:
        techniques = lift.get_techniques(stix_format=False)
        progress_callback(50)
    except Exception as e:
        messagebox.showerror("Error", f"Error fetching techniques from MITRE ATT&CK database: {e}")
        return

    # Process techniques and compute similarities
    technique_details = []
    for technique in techniques:
        technique_details.append({
            'id': technique.get('technique_id', 'No ID'),
            'name': technique.get('technique', 'No Name'),
            'description': technique.get('technique_description', 'No Description'),
            'tactic': ', '.join(technique.get('tactic', []))
        })

    descriptions_embeddings = model.encode([detail['description'] for detail in technique_details], convert_to_tensor=True)
    similarities = util.pytorch_cos_sim(sentence_embedding, descriptions_embeddings)

    # Select top 3 matches based on similarity
    top_matches_indices = np.argsort(-similarities[0])[:3]
    top_matches = [{**technique_details[index], 'similarity': similarities[0][index].item()} for index in top_matches_indices]

    # Format and send results to the queue
    result_text = "\n\n".join([f"ID: {match['id']}\nName: {match['name']}\nTactic: {match['tactic']}\nSimilarity: {match['similarity']:.4f}" for match in top_matches])
    result_queue.put(result_text)
    progress_callback(100)

def update_progress(value):
    """
    Updates the progress bar in the GUI.
    """
    progress_bar['value'] = value
    root.update_idletasks()

def on_submit():
    """
    Handles the submit action: fetches the sentence, resets UI components, and starts background processing.
    """
    sentence = entry_sentence.get("1.0", "end-1c")
    if not sentence.strip():
        messagebox.showinfo("Info", "Please enter a sentence.")
        return

    progress_bar['value'] = 0
    result_text.delete('1.0', tk.END)
    threading.Thread(target=lambda: find_similar_techniques(sentence, update_progress, result_queue)).start()

def check_queue():
    """
    Periodically checks the queue for results and updates the GUI with any new results.
    """
    try:
        result = result_queue.get_nowait()
        result_text.insert(tk.END, result)
    except Empty:
        pass
    root.after(100, check_queue)

# GUI setup
root = tk.Tk()
root.title("AI MITRE ATT&CK Technique Correlation")

# Input sentence text area
tk.Label(root, text="Enter a sentence describing a cybersecurity attack:").pack()
entry_sentence = scrolledtext.ScrolledText(root, height=5)
entry_sentence.pack()

# Submit button
submit_button = tk.Button(root, text="Submit", command=on_submit)
submit_button.pack()

# Progress bar
progress_bar = ttk.Progressbar(root, orient=tk.HORIZONTAL, length=400, mode='determinate')
progress_bar.pack()

# Results display area
tk.Label(root, text="Top 3 Technique Matches:").pack()
result_text = scrolledtext.ScrolledText(root, height=10)
result_text.pack()

# Queue for thread-safe communication between background thread and GUI
result_queue = Queue()
root.after(100, check_queue)

root.mainloop()
