"""Retrain and save the model:  python train_model.py"""
import ipl_core as core

df = core.load_history()
core.train_and_save(df)
print("Saved", core.MODEL_FILE, "trained on", len(df), "matches")
