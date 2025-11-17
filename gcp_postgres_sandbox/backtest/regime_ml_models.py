"""
Regime ML Models: Walk-Forward Training & Prediction
===================================================

Train and evaluate three model types for regime prediction:
1. Baseline Rule-Based Classifier
2. Gradient Boosting Classifier
3. Random Forest Classifier

Models predict "bad market" (regime=1) at 24h, 48h, 72h horizons.

Walk-forward validation ensures NO look-ahead bias:
- Training: Historical data
- Validation: Subsequent period (untouched during training)
- Test: Final period for out-of-sample evaluation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import sys
import pickle
import warnings

warnings.filterwarnings('ignore')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import get_db_engines
from backtest.utils.database_utils import safe_query

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, classification_report, roc_curve
)
from sklearn.model_selection import TimeSeriesSplit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

HORIZONS = ['24h', '48h', '72h']
MODEL_TYPES = ['baseline', 'gradient_boosting', 'random_forest']

# Walk-forward split dates (strict time-based, NO LOOK-AHEAD)
TRAIN_END = pd.Timestamp('2025-07-31', tz='UTC')
VAL_START = pd.Timestamp('2025-08-01', tz='UTC')
VAL_END = pd.Timestamp('2025-08-31', tz='UTC')
TEST_START = pd.Timestamp('2025-09-01', tz='UTC')

# Feature columns to exclude from model training
EXCLUDE_COLS = ['slug', 'timestamp', 'close', 'return_24h', 'return_48h', 'return_72h']


# ============================================================================
# DATA PREPARATION
# ============================================================================

class ModelDataPreparation:
    """Prepare training data with no look-ahead bias"""

    def __init__(self):
        """Initialize database connection"""
        try:
            engines = get_db_engines()
            self.engine_backtest = engines[2]
            logger.info("✓ Database connection established")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise

    def load_training_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load features and labels for model training.

        Returns:
            Tuple of (features_df, labels_df)
        """
        logger.info("=" * 80)
        logger.info("LOADING TRAINING DATA (NO LOOK-AHEAD BIAS)")
        logger.info("=" * 80)

        try:
            # Load features
            logger.info("Loading features from regime_features table...")
            features_query = """
            SELECT * FROM regime_features
            ORDER BY timestamp, slug
            """
            df_features = safe_query(self.engine_backtest, features_query)
            df_features['timestamp'] = pd.to_datetime(df_features['timestamp'], utc=True)

            logger.info(f"✓ Loaded {len(df_features):,.0f} feature records")
            logger.info(f"✓ Feature columns: {len(df_features.columns)}")

            # Load labels (forward returns & regime)
            logger.info("Loading labels from regime_forward_returns table...")
            labels_query = """
            SELECT slug, timestamp, return_24h, return_48h, return_72h,
                   regime_24h, regime_48h, regime_72h
            FROM regime_forward_returns
            ORDER BY timestamp, slug
            """
            df_labels = safe_query(self.engine_backtest, labels_query)
            df_labels['timestamp'] = pd.to_datetime(df_labels['timestamp'], utc=True)

            logger.info(f"✓ Loaded {len(df_labels):,.0f} label records")

            # Merge features and labels
            df_merged = df_features.merge(
                df_labels,
                on=['slug', 'timestamp'],
                how='inner'
            )

            logger.info(f"✓ Merged: {len(df_merged):,.0f} complete records")

            # Check data quality
            logger.info(f"\nData Quality Checks:")
            for horizon in HORIZONS:
                regime_col = f'regime_{horizon}'
                bad_count = (df_merged[regime_col] == 1).sum()
                normal_count = (df_merged[regime_col] == 0).sum()
                total = bad_count + normal_count
                pct_bad = 100 * bad_count / total
                logger.info(f"  {horizon}: {bad_count:,} BAD ({pct_bad:.1f}%), {normal_count:,} NORMAL")

            return df_features, df_labels, df_merged

        except Exception as e:
            logger.error(f"✗ Data loading failed: {e}")
            raise

    def split_walk_forward(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into train/validation/test sets using strict timestamps.

        NO OVERLAP - each set uses only its designated time period.
        """
        logger.info("=" * 80)
        logger.info("WALK-FORWARD TIME SPLIT")
        logger.info("=" * 80)

        train_mask = df['timestamp'] <= TRAIN_END
        val_mask = (df['timestamp'] >= VAL_START) & (df['timestamp'] <= VAL_END)
        test_mask = df['timestamp'] >= TEST_START

        df_train = df[train_mask].copy()
        df_val = df[val_mask].copy()
        df_test = df[test_mask].copy()

        logger.info(f"Training set:   {df_train['timestamp'].min()} to {df_train['timestamp'].max()} ({len(df_train):,} records)")
        logger.info(f"Validation set: {df_val['timestamp'].min()} to {df_val['timestamp'].max()} ({len(df_val):,} records)")
        logger.info(f"Test set:       {df_test['timestamp'].min()} to {df_test['timestamp'].max()} ({len(df_test):,} records)")

        return df_train, df_val, df_test

    @staticmethod
    def get_feature_columns(df: pd.DataFrame) -> List[str]:
        """Get all valid feature columns (exclude metadata and labels)"""
        exclude = set(EXCLUDE_COLS + [f'regime_{h}' for h in HORIZONS] +
                     [f'return_{h}' for h in HORIZONS])
        return [col for col in df.columns if col not in exclude]

    @staticmethod
    def prepare_xy(df: pd.DataFrame, label_col: str, feature_cols: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare X (features) and y (labels) arrays"""
        # Handle missing values
        df_clean = df[feature_cols + [label_col]].dropna()

        X = df_clean[feature_cols].values
        y = df_clean[label_col].values

        logger.info(f"    Features shape: {X.shape}")
        logger.info(f"    Labels shape: {y.shape}")
        logger.info(f"    Class balance: {(y==1).sum()} BAD, {(y==0).sum()} NORMAL")

        return X, y


# ============================================================================
# BASELINE MODEL
# ============================================================================

class BaselineRuleModel:
    """Simple rule-based classifier for baseline comparison"""

    def __init__(self):
        self.name = 'baseline'

    def predict(self, X: np.ndarray, feature_cols: List[str]) -> np.ndarray:
        """
        Predict regime using simple threshold rules.

        Rule: If critical_combined=1 OR (share_poor>0.75 AND net_conviction<-80 AND dmv<-15)
              then predict BAD (1), else NORMAL (0)
        """
        # Requires converting back to DataFrame with feature names
        df_temp = pd.DataFrame(X, columns=feature_cols)

        predictions = np.zeros(len(X))

        # Critical combined flag
        if 'critical_combined' in feature_cols:
            idx = feature_cols.index('critical_combined')
            predictions = np.where(X[:, idx] == 1, 1, predictions)

        # Fallback rule
        if all(col in feature_cols for col in ['share_poor', 'conviction_collapse_flag', 'critical_dmv_collapse']):
            share_poor_idx = feature_cols.index('share_poor')
            conviction_idx = feature_cols.index('conviction_collapse_flag')
            dmv_idx = feature_cols.index('critical_dmv_collapse')

            mask = (X[:, share_poor_idx] > 0.75) & (X[:, conviction_idx] == 1) & (X[:, dmv_idx] == 1)
            predictions = np.where(mask, 1, predictions)

        return predictions.astype(int)

    def predict_proba(self, X: np.ndarray, feature_cols: List[str]) -> np.ndarray:
        """Return probability estimates (0 or 1)"""
        preds = self.predict(X, feature_cols)
        return np.column_stack([1 - preds, preds])


# ============================================================================
# GRADIENT BOOSTING MODEL
# ============================================================================

class RegimeGradientBoostingModel:
    """Gradient Boosting model for regime prediction"""

    def __init__(self):
        self.name = 'gradient_boosting'
        self.model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_split=100,
            min_samples_leaf=50,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.feature_names = None

    def fit(self, X: np.ndarray, y: np.ndarray, feature_cols: List[str]):
        """Train the model"""
        logger.info("    Training Gradient Boosting...")

        # Normalize features
        X_scaled = self.scaler.fit_transform(X)

        # Train with class weight for imbalance
        self.model.fit(X_scaled, y)
        self.feature_names = feature_cols

        logger.info(f"    ✓ Model trained on {len(X)} samples")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return probability estimates"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)

    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature importance scores"""
        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        return importance_df


# ============================================================================
# RANDOM FOREST MODEL
# ============================================================================

class RegimeRandomForestModel:
    """Random Forest model for regime prediction"""

    def __init__(self):
        self.name = 'random_forest'
        self.model = RandomForestClassifier(
            n_estimators=300,
            max_depth=10,
            min_samples_split=50,
            min_samples_leaf=25,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )
        self.scaler = StandardScaler()
        self.feature_names = None

    def fit(self, X: np.ndarray, y: np.ndarray, feature_cols: List[str]):
        """Train the model"""
        logger.info("    Training Random Forest...")

        # Normalize features
        X_scaled = self.scaler.fit_transform(X)

        # Train with class weight for imbalance
        self.model.fit(X_scaled, y)
        self.feature_names = feature_cols

        logger.info(f"    ✓ Model trained on {len(X)} samples")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return probability estimates"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)

    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature importance scores"""
        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        return importance_df


# ============================================================================
# MODEL EVALUATION
# ============================================================================

class ModelEvaluator:
    """Evaluate model performance"""

    @staticmethod
    def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray, horizon: str, model_name: str) -> Dict:
        """
        Evaluate model predictions comprehensively.

        Returns:
            Dictionary with all evaluation metrics
        """
        metrics = {
            'horizon': horizon,
            'model': model_name,
            'total_samples': len(y_true),
            'bad_count': (y_true == 1).sum(),
            'normal_count': (y_true == 0).sum(),
        }

        # Classification metrics
        metrics['accuracy'] = float(np.mean(y_pred == y_true))
        metrics['precision'] = float(precision_score(y_true, y_pred, zero_division=0))
        metrics['recall'] = float(recall_score(y_true, y_pred, zero_division=0))
        metrics['f1'] = float(f1_score(y_true, y_pred, zero_division=0))

        # ROC-AUC (if probabilities available)
        if y_proba is not None:
            try:
                metrics['roc_auc'] = float(roc_auc_score(y_true, y_proba[:, 1]))
            except:
                metrics['roc_auc'] = np.nan
        else:
            metrics['roc_auc'] = np.nan

        # Confusion matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        metrics['true_negatives'] = int(tn)
        metrics['false_positives'] = int(fp)
        metrics['false_negatives'] = int(fn)
        metrics['true_positives'] = int(tp)

        # False positive/negative rates
        metrics['false_positive_rate'] = float(fp / (fp + tn)) if (fp + tn) > 0 else 0
        metrics['false_negative_rate'] = float(fn / (fn + tp)) if (fn + tp) > 0 else 0

        return metrics

    @staticmethod
    def log_evaluation(metrics: Dict):
        """Log evaluation metrics"""
        logger.info(f"\n    Horizon: {metrics['horizon']} | Model: {metrics['model']}")
        logger.info(f"    Accuracy:  {metrics['accuracy']:.3f}")
        logger.info(f"    Precision: {metrics['precision']:.3f} (of predicted BAD, how many correct?)")
        logger.info(f"    Recall:    {metrics['recall']:.3f} (of actual BAD, how many caught?)")
        logger.info(f"    F1-Score:  {metrics['f1']:.3f}")
        logger.info(f"    ROC-AUC:   {metrics['roc_auc']:.3f}")
        logger.info(f"    False Positive Rate: {metrics['false_positive_rate']:.3f}")
        logger.info(f"    False Negative Rate: {metrics['false_negative_rate']:.3f}")


# ============================================================================
# MAIN TRAINING PIPELINE
# ============================================================================

class RegimeModelTrainer:
    """Complete training pipeline"""

    def __init__(self):
        self.data_prep = ModelDataPreparation()
        self.evaluator = ModelEvaluator()
        self.models = {}
        self.results = []

    def train_all_models(self):
        """Train all model types for all horizons"""
        logger.info("\n" + "=" * 80)
        logger.info("REGIME MODEL TRAINING - WALK-FORWARD VALIDATION")
        logger.info("=" * 80)

        try:
            # Load data
            df_features, df_labels, df_merged = self.data_prep.load_training_data()

            # Split into train/val/test
            df_train, df_val, df_test = self.data_prep.split_walk_forward(df_merged)

            # Get feature columns
            feature_cols = self.data_prep.get_feature_columns(df_merged)
            logger.info(f"\n✓ Using {len(feature_cols)} features for training")

            # Train models for each horizon
            for horizon in HORIZONS:
                logger.info(f"\n" + "-" * 80)
                logger.info(f"TRAINING MODELS FOR {horizon} HORIZON")
                logger.info("-" * 80)

                label_col = f'regime_{horizon}'

                # Prepare training data
                logger.info(f"\nPreparing training data...")
                X_train, y_train = self.data_prep.prepare_xy(df_train, label_col, feature_cols)

                # Prepare validation data
                logger.info(f"Preparing validation data...")
                X_val, y_val = self.data_prep.prepare_xy(df_val, label_col, feature_cols)

                # Prepare test data
                logger.info(f"Preparing test data...")
                X_test, y_test = self.data_prep.prepare_xy(df_test, label_col, feature_cols)

                # Train baseline
                logger.info(f"\nTraining Baseline rule-based model...")
                baseline = BaselineRuleModel()
                y_pred_baseline = baseline.predict(X_val, feature_cols)
                metrics_baseline = self.evaluator.evaluate_predictions(
                    y_val, y_pred_baseline, None, horizon, 'baseline'
                )
                self.evaluator.log_evaluation(metrics_baseline)
                self.results.append(metrics_baseline)

                # Train Gradient Boosting
                logger.info(f"\nTraining Gradient Boosting model...")
                gb_model = RegimeGradientBoostingModel()
                gb_model.fit(X_train, y_train, feature_cols)
                y_pred_gb = gb_model.predict(X_val)
                y_proba_gb = gb_model.predict_proba(X_val)
                metrics_gb = self.evaluator.evaluate_predictions(
                    y_val, y_pred_gb, y_proba_gb, horizon, 'gradient_boosting'
                )
                self.evaluator.log_evaluation(metrics_gb)
                self.results.append(metrics_gb)

                # Train Random Forest
                logger.info(f"\nTraining Random Forest model...")
                rf_model = RegimeRandomForestModel()
                rf_model.fit(X_train, y_train, feature_cols)
                y_pred_rf = rf_model.predict(X_val)
                y_proba_rf = rf_model.predict_proba(X_val)
                metrics_rf = self.evaluator.evaluate_predictions(
                    y_val, y_pred_rf, y_proba_rf, horizon, 'random_forest'
                )
                self.evaluator.log_evaluation(metrics_rf)
                self.results.append(metrics_rf)

                # Store models
                self.models[horizon] = {
                    'baseline': baseline,
                    'gradient_boosting': gb_model,
                    'random_forest': rf_model,
                    'feature_cols': feature_cols
                }

                # Feature importance
                logger.info(f"\nTop 10 features (Gradient Boosting {horizon}):")
                importance_gb = gb_model.get_feature_importance()
                for idx, row in importance_gb.head(10).iterrows():
                    logger.info(f"  {row['feature']:40s}: {row['importance']:.4f}")

                logger.info(f"\nTop 10 features (Random Forest {horizon}):")
                importance_rf = rf_model.get_feature_importance()
                for idx, row in importance_rf.head(10).iterrows():
                    logger.info(f"  {row['feature']:40s}: {row['importance']:.4f}")

            # Save results
            self.save_results()

            logger.info("\n" + "=" * 80)
            logger.info("✅ MODEL TRAINING COMPLETE")
            logger.info("=" * 80)

            return True

        except Exception as e:
            logger.error(f"\n✗ Training failed: {e}")
            raise

    def save_results(self):
        """Save results and models to disk"""
        logger.info("\n" + "=" * 80)
        logger.info("SAVING RESULTS")
        logger.info("=" * 80)

        output_dir = Path(__file__).parent / 'models'
        output_dir.mkdir(exist_ok=True)

        # Save results CSV
        df_results = pd.DataFrame(self.results)
        results_file = output_dir / 'training_results.csv'
        df_results.to_csv(results_file, index=False)
        logger.info(f"✓ Results saved to {results_file}")

        # Save models
        for horizon, model_dict in self.models.items():
            horizon_dir = output_dir / horizon
            horizon_dir.mkdir(exist_ok=True)

            for model_type, model in model_dict.items():
                if model_type != 'feature_cols':
                    model_file = horizon_dir / f'{model_type}.pkl'
                    with open(model_file, 'wb') as f:
                        pickle.dump(model, f)
                    logger.info(f"✓ Saved {model_type} for {horizon}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution"""
    try:
        trainer = RegimeModelTrainer()
        trainer.train_all_models()
        return True
    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
