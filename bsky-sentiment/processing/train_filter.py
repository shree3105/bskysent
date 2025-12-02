import pandas as pd
import torch
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments, DataCollatorWithPadding
from datasets import Dataset
import logging
import os

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
MODEL_NAME = "answerdotai/ModernBERT-base"
OUTPUT_DIR = "./bsky-sentiment/models/noise_filter_v1"
# Use absolute path or relative to the script location for robustness
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "labeled_dataset.csv")

def compute_metrics(pred):
    labels = pred.label_ids
    preds = pred.predictions.argmax(-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='binary')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

def train():
    # 1. Load Data
    logger.info(f"Loading labeled dataset from {DATA_PATH}...")
    if not os.path.exists(DATA_PATH):
        logger.error(f"File not found: {DATA_PATH}. Please check the path.")
        return

    df = pd.read_csv(DATA_PATH)

    # Filter errors and map labels
    df = df[df['label'].isin(["Financial News", "Noise"])]
    label_map = {"Noise": 0, "Financial News": 1}
    df['labels'] = df['label'].map(label_map)
    
    # Check for class balance
    logger.info(f"Class distribution:\n{df['labels'].value_counts()}")

    # Split
    train_df, eval_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df['labels'])
    
    # Convert to HuggingFace Dataset
    train_dataset = Dataset.from_pandas(train_df)
    eval_dataset = Dataset.from_pandas(eval_df)
    
    # 2. Tokenize
    logger.info(f"Loading Tokenizer ({MODEL_NAME})...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    
    def tokenize_function(examples):
        return tokenizer(examples["full_text"], padding="max_length", truncation=True, max_length=256)
    
    tokenized_train = train_dataset.map(tokenize_function, batched=True)
    tokenized_eval = eval_dataset.map(tokenize_function, batched=True)
    
    # Remove raw text columns to avoid collator errors
    cols_to_remove = [c for c in tokenized_train.column_names if c not in ["input_ids", "attention_mask", "labels"]]
    tokenized_train = tokenized_train.remove_columns(cols_to_remove)
    tokenized_eval = tokenized_eval.remove_columns(cols_to_remove)
    
    # 3. Model
    logger.info("Loading Model...")
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
    
    # 4. Training Args
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=3,
        weight_decay=0.01,
        logging_dir='./logs',
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        save_total_limit=2,
        fp16=torch.cuda.is_available(), # Use Mixed Precision if GPU is available
        report_to="none" # Disable wandb/mlflow for now unless requested
    )
    
    # 5. Train
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        compute_metrics=compute_metrics,
    )
    
    logger.info("Starting Training...")
    trainer.train()
    
    # 6. Save
    logger.info(f"Saving model to {OUTPUT_DIR}...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    
    # Evaluate final model
    logger.info("Evaluating final model...")
    metrics = trainer.evaluate()
    logger.info(f"Final Metrics: {metrics}")
    
    logger.info("Done!")

if __name__ == "__main__":
    train()
