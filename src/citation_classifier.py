#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Machine Learning Citation Classifier

This module provides functionality to train and use a machine learning model
to classify citations as reliable or unreliable based on patterns in their format,
content, and context. This reduces the need for API calls to verify citations.
"""

import os
import re
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Path to the citation database and model files
DOWNLOAD_DIR = "downloaded_briefs"
UNCONFIRMED_CITATIONS_FILE = os.path.join(
    DOWNLOAD_DIR, "unconfirmed_citations_flat.json"
)
MODEL_FILE = os.path.join(DOWNLOAD_DIR, "citation_classifier_model.pkl")
VECTORIZER_FILE = os.path.join(DOWNLOAD_DIR, "citation_vectorizer.pkl")


# Features to extract from citations
def extract_features_from_citation(citation_text, canonical_name=None):
    """Extract features from citation text for classification."""
    features = {}
    
    # Basic citation features
    features["length"] = len(citation_text)
    features["has_case_name"] = 1 if canonical_name and len(canonical_name) > 0 else 0
    if canonical_name:
        features["canonical_name_length"] = len(canonical_name)
    else:
        features["canonical_name_length"] = 0

    # Check for common citation patterns
    features["has_volume_reporter_page"] = (
        1 if re.search(r"\d+\s+[A-Za-z\.]+\s+\d+", citation_text) else 0
    )
    features["has_year"] = 1 if re.search(r"\(\d{4}\)", citation_text) else 0
    features["has_court_abbreviation"] = (
        1
        if re.search(
            r"\b(S\.\s*Ct\.|F\.\s*\d+d|U\.\s*S\.|P\.\s*\d+d|Wn\.\s*\d+d|Wn\.\s*App\.)",
            citation_text,
            re.IGNORECASE,
        )
        else 0
    )

    # Check for WL citation format
    features["is_wl_citation"] = (
        1 if re.search(r"\d{4}\s+WL\s+\d+", citation_text) else 0
    )

    # Check for common unreliable patterns
    features["has_unusual_characters"] = (
        1 if re.search(r"[^\w\s\.,;\(\)\[\]\-]", citation_text) else 0
    )
    features["has_excessive_numbers"] = (
        1 if len(re.findall(r"\d+", citation_text)) > 5 else 0
    )

    # Extract reporter information
    reporter_match = re.search(r"([A-Za-z]+\.(?:\s*\d+)?[A-Za-z]*)", citation_text)
    features["has_valid_reporter"] = 0

    if reporter_match:
        reporter = reporter_match.group(1).lower()
        # Check for common reporters
        common_reporters = [
            "f.",
            "f.2d",
            "f.3d",
            "u.s.",
            "s.ct.",
            "l.ed.",
            "p.",
            "p.2d",
            "p.3d",
            "wn.",
            "wn.2d",
            "wn.app.",
            "wash.",
            "wash.2d",
            "wash.app.",
        ]
        features["has_valid_reporter"] = (
            1 if any(r in reporter for r in common_reporters) else 0
        )

    return features


def prepare_citation_data(citations):
    """Prepare citation data for training the model."""
    data = []
    labels = []
    texts = []

    for citation in citations:
        # Skip citations without confidence scores
        if "confidence" not in citation:
            continue

        # Extract features
        features = extract_features_from_citation(
            citation.get("citation_text", ""), citation.get("canonical_name", "")
        )

        # Create label (1 for reliable, 0 for unreliable)
        # Citations with confidence >= 0.7 are considered reliable
        label = 1 if citation.get("confidence", 0) >= 0.7 else 0

        # Add to datasets
        data.append(features)
        labels.append(label)
        texts.append(citation.get("citation_text", ""))

    return pd.DataFrame(data), np.array(labels), texts


def train_citation_classifier():
    """Train a machine learning model to classify citations."""
    logger.info("Loading citation data...")
    try:
        with open(UNCONFIRMED_CITATIONS_FILE, "r", encoding="utf-8") as f:
            citations = json.load(f)
    except Exception as e:
        logger.error(f"Error loading citation data: {e}")
        return None, None

    # Check if we have enough data
    if len(citations) < 50:
        logger.info(f"Not enough citation data to train a model. Found only {len(citations)} citations."
        )
        return None, None

    logger.info(f"Preparing data from {len(citations)} citations...")
    features_df, labels, texts = prepare_citation_data(citations)

    # Create text features using TF-IDF
    logger.info("Creating text features...")
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(2, 5), max_features=200
    )
    vectorizer.fit_transform(texts)

    # Convert DataFrame to numpy array
    feature_array = features_df.to_numpy()

    # Split data into training and testing sets
    X_train, X_test, y_train, y_test, texts_train, texts_test = train_test_split(
        feature_array, labels, texts, test_size=0.2, random_state=42
    )

    # Create text features for training and testing
    X_text_train = vectorizer.transform(texts_train)
    X_text_test = vectorizer.transform(texts_test)

    # Train the model
    logger.info("Training the classifier...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_text_train, y_train)

    # Evaluate the model
    y_pred = model.predict(X_text_test)
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"Model accuracy: {accuracy:.2f}")
    logger.info(classification_report(y_test, y_pred))

    # Save the model and vectorizer
    logger.info("Saving model and vectorizer...")
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model, f)

    with open(VECTORIZER_FILE, "wb") as f:
        pickle.dump(vectorizer, f)

    logger.info(f"Model and vectorizer saved to {DOWNLOAD_DIR}")
    return model, vectorizer


def load_citation_classifier():
    """Load the trained citation classifier model."""
    try:
        # Check if model and vectorizer files exist
        if not os.path.exists(MODEL_FILE) or not os.path.exists(VECTORIZER_FILE):
            logger.info("Model or vectorizer file not found. Training new model...")
            return train_citation_classifier()

        # Load model and vectorizer
        with open(MODEL_FILE, "rb") as f:
            model = pickle.load(f)

        with open(VECTORIZER_FILE, "rb") as f:
            vectorizer = pickle.load(f)

        logger.info("Citation classifier model loaded successfully.")
        return model, vectorizer
    except Exception as e:
        logger.error(f"Error loading citation classifier: {e}")
        return None, None


def classify_citation(citation_text, canonical_name=None):
    """
    Classify a citation as reliable or unreliable using the trained model.
    Returns a confidence score between 0.0 and 1.0.
    """
    # Load the model and vectorizer
    model, vectorizer = load_citation_classifier()

    if model is None or vectorizer is None:
        logger.info("Could not load or train the citation classifier model.")
        return 0.5  # Return neutral confidence if model is unavailable

    try:
        # Extract features
        features = extract_features_from_citation(citation_text, canonical_name)

        # Create text features
        text_features = vectorizer.transform([citation_text])

        # Get prediction probability
        try:
            proba = model.predict_proba(text_features)

            # Initialize default confidence
            confidence = 0.5

            # Handle different shapes of predict_proba output
            if hasattr(proba, "shape"):
                if len(proba.shape) > 1 and proba.shape[0] > 0:
                    if proba.shape[1] > 1:
                        # Standard case: 2D array with probabilities for each class
                        confidence = float(
                            proba[0, 1]
                        )  # Probability of reliable class (index 1)
                    else:
                        # Single class probability
                        confidence = float(proba[0, 0])
                elif len(proba.shape) == 1 and len(proba) > 0:
                    # Case: 1D array (binary classification with shape [n_samples])
                    confidence = float(proba[0])
            elif isinstance(proba, (list, np.ndarray)) and len(proba) > 0:
                # Handle list or array input
                if len(proba) > 1:
                    # Multiple classes - take the last probability if more than one class
                    confidence = float(proba[-1])
                else:
                    # Single probability
                    confidence = float(proba[0])
            else:
                # Fallback to prediction if proba is in an unexpected format
                prediction = model.predict(text_features)
                confidence = (
                    float(prediction[0])
                    if hasattr(prediction, "__len__") and len(prediction) > 0
                    else 0.5
                )
        except (IndexError, TypeError, AttributeError) as e:
            logger.error(f"Error processing prediction probabilities: {e}")
            try:
                # Fallback to prediction if proba fails
                prediction = model.predict(text_features)
                confidence = (
                    float(prediction[0])
                    if hasattr(prediction, "__len__") and len(prediction) > 0
                    else 0.5
                )
            except Exception as e2:
                logger.error(f"Fallback prediction also failed: {e2}")
                confidence = 0.5

        # Adjust confidence based on feature heuristics
        if features["has_valid_reporter"] == 0:
            confidence *= 0.8  # Reduce confidence if no valid reporter

        if features["is_wl_citation"] == 1:
            confidence *= 0.9  # Slightly reduce confidence for WL citations

        if features["has_unusual_characters"] == 1:
            confidence *= 0.7  # Reduce confidence for unusual characters

        return confidence
    except Exception as e:
        logger.error(f"Error classifying citation: {e}")
        return 0.5  # Return neutral confidence on error


def batch_classify_citations(citations):
    """
    Classify multiple citations and return confidence scores.
    """
    # Load the model and vectorizer
    model, vectorizer = load_citation_classifier()

    if model is None or vectorizer is None:
        logger.info("Could not load or train the citation classifier model.")
        return [0.5] * len(citations)  # Return neutral confidence for all

    try:
        # Extract text and features
        texts = [c.get("citation_text", "") for c in citations]
        if not texts:  # Handle empty input
            return []

        # Create text features
        text_features = vectorizer.transform(texts)

        # Get prediction probabilities
        try:
            probas = model.predict_proba(text_features)

            # Initialize confidences with default value
            confidences = [0.5] * len(texts)

            # Process probabilities based on their shape
            confidences = [0.5] * len(texts)  # Initialize with default confidence

            try:
                if hasattr(probas, "shape"):
                    if len(probas.shape) == 2 and probas.shape[0] > 0:
                        if probas.shape[1] > 1:
                            # Standard case: 2D array with probabilities for each class
                            confidences = [
                                float(p[-1]) for p in probas
                            ]  # Take last probability
                        else:
                            # Single class probability
                            confidences = [float(p[0]) for p in probas]
                    elif len(probas.shape) == 1:
                        # 1D array of probabilities
                        confidences = [float(p) for p in probas]
                elif isinstance(probas, (list, np.ndarray)) and len(probas) > 0:
                    # Handle list or array input
                    confidences = []
                    for p in probas:
                        try:
                            if hasattr(p, "__len__") and len(p) > 1:
                                # Take the last probability if multiple classes
                                confidences.append(float(p[-1]))
                            else:
                                # Single probability or empty array
                                confidences.append(
                                    float(p[0])
                                    if hasattr(p, "__len__") and len(p) > 0
                                    else 0.5
                                )
                        except (IndexError, TypeError, ValueError) as e:
                            logger.error(f"Error processing probability: {e}")
                            confidences.append(0.5)
            except Exception as e:
                logger.error(f"Error processing batch probabilities: {e}")
                # Fallback to prediction if proba fails
                try:
                    predictions = model.predict(text_features)
                    confidences = (
                        [float(p) for p in predictions]
                        if hasattr(predictions, "__len__")
                        else [0.5] * len(texts)
                    )
                except Exception as e2:
                    logger.error(f"Fallback prediction also failed: {e2}")
                    confidences = [0.5] * len(texts)
        except Exception as e:
            logger.error(f"Error in batch prediction: {e}")
            confidences = [0.5] * len(texts)

        # Adjust confidence based on feature heuristics
        for i, citation in enumerate(citations):
            try:
                features = extract_features_from_citation(
                    citation.get("citation_text", ""), citation.get("canonical_name", "")
                )

                if features["has_valid_reporter"] == 0:
                    confidences[i] *= 0.8  # Reduce confidence if no valid reporter

                if features["is_wl_citation"] == 1:
                    confidences[i] *= 0.9  # Slightly reduce confidence for WL citations

                if features["has_unusual_characters"] == 1:
                    confidences[i] *= 0.7  # Reduce confidence for unusual characters
            except Exception as e:
                logger.error(f"Error processing citation features: {e}")

        return confidences
    except Exception as e:
        logger.error(f"Error batch classifying citations: {e}")
        return [0.5] * len(citations)  # Return neutral confidence on error


if __name__ == "__main__":
    # Train the citation classifier
    logger.info("Training citation classifier...")
    train_citation_classifier()

    # Test the classifier on a few examples
    test_citations = [
        "550 U.S. 544 (2007)",  # Should be high confidence
        "123 Fake Reporter 456",  # Should be low confidence
        "2020 WL 123456",  # Should be medium confidence
        "Wn.2d 123, 456 P.3d 789 (2019)",  # Should be high confidence
    ]

    logger.info("\nTesting classifier on examples:")
    for citation in test_citations:
        confidence = classify_citation(citation)
        logger.info(f"Citation: {citation}")
        logger.info(f"Confidence: {confidence:.2f}")
        logger.info(f"Classification: {'Reliable' if confidence >= 0.7 else 'Unreliable'}")
        logger.info()
