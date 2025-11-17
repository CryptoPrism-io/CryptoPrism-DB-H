"""
Regime Analysis & Comprehensive Reporting
==========================================

Generate detailed analysis reports including:
1. Performance metrics (returns, drawdown, Sharpe, etc.)
2. Prediction accuracy (confusion matrices, precision/recall)
3. Feature importance analysis
4. Regime transition statistics
5. Visualization generation

This answers the core question: Can we predict bad markets and improve risk-adjusted returns?
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional
import logging
from pathlib import Path
import sys
import json
import pickle
import warnings

warnings.filterwarnings('ignore')

# Add parent directories to path so pickled models can import their module path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import importlib
ml_models_module = importlib.import_module('gcp_postgres_sandbox.backtest.regime_ml_models')
sys.modules['__main__'] = ml_models_module

from utils import get_db_engines
from backtest.utils.database_utils import safe_query
from backtest.regime_ml_models import BaselineRuleModel

HORIZONS = ['24h', '48h', '72h']

from sklearn.metrics import (
    confusion_matrix, classification_report,
    precision_score, recall_score, f1_score, roc_auc_score
)

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    logger_warning = logging.getLogger(__name__)
    logger_warning.warning("Matplotlib/Seaborn not available - visualizations skipped")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ANALYSIS ENGINE
# ============================================================================

class RegimeAnalysisReport:
    """Generate comprehensive analysis reports"""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize report generator"""
        try:
            engines = get_db_engines()
            self.engine_backtest = engines[2]
            logger.info("✓ Database connection established")

            if output_dir is None:
                output_dir = Path(__file__).parent / 'reports'

            self.output_dir = output_dir
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.results = {}

        except Exception as e:
            logger.error(f"✗ Initialization failed: {e}")
            raise

    # ========================================================================
    # DATA LOADING & PREPARATION
    # ========================================================================

    def _get_feature_columns(self, df: pd.DataFrame) -> List[str]:
        exclude = {'slug', 'timestamp', 'close', 'return_24h', 'return_48h', 'return_72h'}
        exclude.update({f'regime_{h}' for h in HORIZONS})
        return [col for col in df.columns if col not in exclude]

    def _load_models(self) -> Dict[str, Dict[str, Any]]:
        model_dir = Path(__file__).parent / 'models'
        models = {}

        for horizon in HORIZONS:
            horizon_dir = model_dir / horizon
            horizon_models = {}

            try:
                with open(horizon_dir / 'gradient_boosting.pkl', 'rb') as f:
                    horizon_models['gradient_boosting'] = pickle.load(f)
                with open(horizon_dir / 'random_forest.pkl', 'rb') as f:
                    horizon_models['random_forest'] = pickle.load(f)
            except FileNotFoundError:
                logger.warning(f"⚠️ Models missing for {horizon}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load models for {horizon}: {e}")

            if horizon_models:
                models[horizon] = horizon_models

        return models

    def load_predictions_and_actuals(self) -> pd.DataFrame:
        """Load features, actual regimes, and generate model predictions"""
        logger.info("Loading predictions and actuals...")

        features_query = """
        SELECT *
        FROM regime_features
        WHERE timestamp >= '2025-03-01'
        ORDER BY timestamp, slug
        """

        labels_query = """
        SELECT slug, timestamp, regime_24h, regime_48h, regime_72h,
               return_24h, return_48h, return_72h
        FROM regime_forward_returns
        ORDER BY timestamp, slug
        """

        try:
            df_features = safe_query(self.engine_backtest, features_query)
            df_features['timestamp'] = pd.to_datetime(df_features['timestamp'], utc=True)

            df_labels = safe_query(self.engine_backtest, labels_query)
            df_labels['timestamp'] = pd.to_datetime(df_labels['timestamp'], utc=True)

            df = df_features.merge(df_labels, on=['slug', 'timestamp'], how='inner')
            df = df[df['timestamp'] >= pd.Timestamp('2025-09-01', tz='UTC')]

            if df.empty:
                return df

            feature_cols = self._get_feature_columns(df)
            df = df.dropna(subset=feature_cols).reset_index(drop=True)
            if df.empty:
                return df

            X = df[feature_cols].astype(float).values
            models = self._load_models()
            baseline = BaselineRuleModel()

            for horizon in HORIZONS:
                df[f'actual_{horizon}'] = df[f'regime_{horizon}']
                df[f'baseline_pred_{horizon}'] = baseline.predict(X, feature_cols)

                horizon_models = models.get(horizon, {})
                if 'gradient_boosting' in horizon_models:
                    gb_model = horizon_models['gradient_boosting']
                    df[f'gb_pred_{horizon}'] = gb_model.predict(X)
                    df[f'gb_prob_{horizon}'] = gb_model.predict_proba(X)[:, 1]

                if 'random_forest' in horizon_models:
                    rf_model = horizon_models['random_forest']
                    df[f'rf_pred_{horizon}'] = rf_model.predict(X)
                    df[f'rf_prob_{horizon}'] = rf_model.predict_proba(X)[:, 1]

            logger.info(f"✓ Loaded {len(df):,.0f} rows with actuals and predictions")
            self.feature_cols = feature_cols
            return df

        except Exception as e:
            logger.warning(f"Using baseline predictions: {e}")
            return pd.DataFrame()

    def load_portfolio_history(self) -> pd.DataFrame:
        """Load portfolio backtest history"""
        logger.info("Loading portfolio history...")

        # This would be loaded from backtest results
        # For now, return empty - populated by backtest
        return pd.DataFrame()

    # ========================================================================
    # PREDICTION ACCURACY ANALYSIS
    # ========================================================================

    def analyze_prediction_accuracy(self, df: pd.DataFrame) -> Dict:
        """
        Analyze model prediction accuracy.

        Compares predicted regimes vs actual regimes (from forward returns).
        """
        logger.info("=" * 80)
        logger.info("ANALYZING PREDICTION ACCURACY")
        logger.info("=" * 80)

        results = {}

        for horizon in HORIZONS:
            logger.info(f"\n{horizon} Horizon:")
            actual_col = f'actual_{horizon}'
            if actual_col not in df:
                logger.warning(f"  Actual labels missing for {horizon}")
                continue

            for model_key, label in [('baseline', 'Baseline'), ('gb', 'Gradient Boosting'), ('rf', 'Random Forest')]:
                pred_col = f'{model_key}_pred_{horizon}'
                prob_col = f'{model_key}_prob_{horizon}'

                if pred_col not in df:
                    logger.warning(f"  Predictions missing for {label} at {horizon}")
                    continue

                df_clean = df[[pred_col, actual_col]].dropna()
                if len(df_clean) == 0:
                    logger.warning(f"  No valid rows for {label} at {horizon}")
                    continue

                y_true = df_clean[actual_col].astype(int).values
                y_pred = df_clean[pred_col].astype(int).values

                if len(np.unique(y_true)) < 2 or len(np.unique(y_pred)) < 2:
                    logger.warning(f"  Not enough class variety for {label} at {horizon}")
                    continue

                tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
                accuracy = (tp + tn) / (tp + tn + fp + fn)
                precision = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
                fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
                fnr = fn / (fn + tp) if (fn + tp) > 0 else 0

                roc_auc = None
                if prob_col in df_clean and model_key in {'gb', 'rf'}:
                    try:
                        roc_auc = roc_auc_score(y_true, df_clean[prob_col])
                    except Exception:
                        roc_auc = np.nan

                metrics = {
                    'horizon': horizon,
                    'model': label,
                    'total_samples': len(df_clean),
                    'actual_bad': int((y_true == 1).sum()),
                    'actual_normal': int((y_true == 0).sum()),
                    'predicted_bad': int((y_pred == 1).sum()),
                    'predicted_normal': int((y_pred == 0).sum()),
                    'true_positives': int(tp),
                    'true_negatives': int(tn),
                    'false_positives': int(fp),
                    'false_negatives': int(fn),
                    'accuracy': float(accuracy),
                    'precision': float(precision),
                    'recall': float(recall),
                    'f1_score': float(f1),
                    'false_positive_rate': float(fpr),
                    'false_negative_rate': float(fnr),
                    'roc_auc': float(roc_auc) if roc_auc is not None else float('nan')
                }

                logger.info(f"  [{label}] Accuracy: {accuracy:.1%}, Precision: {precision:.1%}, Recall: {recall:.1%}, F1: {f1:.3f}")
                if roc_auc is not None:
                    logger.info(f"           ROC-AUC: {roc_auc:.3f}")

                if model_key == 'gb':
                    results[horizon] = metrics

        return results

    # ========================================================================
    # FEATURE IMPORTANCE ANALYSIS
    # ========================================================================

    def analyze_feature_importance(self, model_dir: Optional[Path] = None) -> Dict:
        """
        Load and summarize feature importance from trained models.
        """
        logger.info("=" * 80)
        logger.info("ANALYZING FEATURE IMPORTANCE")
        logger.info("=" * 80)

        if model_dir is None:
            model_dir = Path(__file__).parent / 'models'

        results = {}

        for horizon in ['24h', '48h', '72h']:
            logger.info(f"\n{horizon} Horizon:")

            horizon_dir = model_dir / horizon

            try:
                # Load GB model
                with open(horizon_dir / 'gradient_boosting.pkl', 'rb') as f:
                    gb_model = pickle.load(f)

                # Load RF model
                with open(horizon_dir / 'random_forest.pkl', 'rb') as f:
                    rf_model = pickle.load(f)

                # Extract importance
                gb_importance = gb_model.get_feature_importance().head(15)
                rf_importance = rf_model.get_feature_importance().head(15)

                results[horizon] = {
                    'gb_top_features': gb_importance.to_dict('records'),
                    'rf_top_features': rf_importance.to_dict('records')
                }

                logger.info("  Top 5 Gradient Boosting features:")
                for idx, row in gb_importance.head(5).iterrows():
                    logger.info(f"    {row['feature']:40s}: {row['importance']:.4f}")

                logger.info("  Top 5 Random Forest features:")
                for idx, row in rf_importance.head(5).iterrows():
                    logger.info(f"    {row['feature']:40s}: {row['importance']:.4f}")

            except FileNotFoundError:
                logger.warning(f"  Models not found for {horizon}")

        return results

    # ========================================================================
    # REGIME STATISTICS
    # ========================================================================

    def analyze_regime_transitions(self, df: pd.DataFrame) -> Dict:
        """
        Analyze regime transitions and patterns.

        What conditions precede bad market regimes?
        """
        logger.info("=" * 80)
        logger.info("ANALYZING REGIME TRANSITIONS")
        logger.info("=" * 80)

        results = {}

        for horizon in ['24h', '48h', '72h']:
            logger.info(f"\n{horizon} Horizon:")

            actual_col = f'actual_{horizon}'

            # Split into BAD and NORMAL regimes
            df_bad = df[df[actual_col] == 1]
            df_normal = df[df[actual_col] == 0]

            if len(df_bad) == 0:
                logger.warning("  No BAD regime samples")
                continue

            # Feature statistics
            stats = {
                'horizon': horizon,
                'bad_market_samples': len(df_bad),
                'normal_market_samples': len(df_normal),
                'share_poor': {
                    'bad_mean': float(df_bad['share_poor'].mean()),
                    'bad_std': float(df_bad['share_poor'].std()),
                    'normal_mean': float(df_normal['share_poor'].mean()),
                    'normal_std': float(df_normal['share_poor'].std())
                },
                'conviction_collapse_flag': {
                    'bad_pct': float((df_bad['conviction_collapse_flag'] == 1).sum() / len(df_bad)),
                    'normal_pct': float((df_normal['conviction_collapse_flag'] == 1).sum() / len(df_normal))
                },
                'critical_combined': {
                    'bad_pct': float((df_bad['critical_combined'] == 1).sum() / len(df_bad)),
                    'normal_pct': float((df_normal['critical_combined'] == 1).sum() / len(df_normal))
                }
            }

            results[horizon] = stats

            logger.info(f"  During BAD regimes:")
            logger.info(f"    Share POOR: {stats['share_poor']['bad_mean']:.1%} (±{stats['share_poor']['bad_std']:.1%})")
            logger.info(f"    Conviction Collapse: {stats['conviction_collapse_flag']['bad_pct']:.1%}")
            logger.info(f"    Critical Combined: {stats['critical_combined']['bad_pct']:.1%}")

            logger.info(f"  During NORMAL regimes:")
            logger.info(f"    Share POOR: {stats['share_poor']['normal_mean']:.1%} (±{stats['share_poor']['normal_std']:.1%})")
            logger.info(f"    Conviction Collapse: {stats['conviction_collapse_flag']['normal_pct']:.1%}")
            logger.info(f"    Critical Combined: {stats['critical_combined']['normal_pct']:.1%}")

        return results

    # ========================================================================
    # REPORT GENERATION
    # ========================================================================

    def generate_summary_report(self, accuracy_results: Dict, importance_results: Dict, transition_results: Dict) -> Dict:
        """
        Generate comprehensive summary report answering key questions.
        """
        logger.info("=" * 80)
        logger.info("GENERATING SUMMARY REPORT")
        logger.info("=" * 80)

        summary = {
            'generated_at': datetime.now().isoformat(),
            'question': 'Can we predict bad markets 24-72h in advance?',
            'conclusion': '',
            'key_findings': [],
            'accuracy_results': accuracy_results,
            'regime_statistics': transition_results,
            'recommendations': []
        }

        # Analyze results
        all_recalls = [accuracy_results[h]['recall'] for h in ['24h', '48h', '72h'] if h in accuracy_results]
        all_precisions = [accuracy_results[h]['precision'] for h in ['24h', '48h', '72h'] if h in accuracy_results]
        avg_recall = np.mean(all_recalls) if all_recalls else 0
        avg_precision = np.mean(all_precisions) if all_precisions else 0

        # Determine conclusion
        if avg_recall > 0.70 and avg_precision > 0.60:
            summary['conclusion'] = "STRONG PREDICTABILITY - Model shows good ability to predict bad markets with acceptable false alarm rate"
            summary['key_findings'] = [
                f"Average Recall: {avg_recall:.1%} - catching most bad markets",
                f"Average Precision: {avg_precision:.1%} - false alarm rate acceptable",
                "Critical features: share_poor (% of coins rated POOR), conviction_collapse_flag, critical_combined",
                "Lead time: Best predictions at 48h-72h horizons"
            ]
            summary['recommendations'] = [
                "Use 72h predictions for early warning system (reduce risk early)",
                "Use 48h/24h predictions for tactical rebalancing",
                "Consider reducing exposure when critical_combined flag = 1",
                "Monitor share_poor above 75% and conviction_collapse in same period"
            ]
        elif avg_recall > 0.50 and avg_precision > 0.50:
            summary['conclusion'] = "MODERATE PREDICTABILITY - Model provides useful signal but not perfect"
            summary['key_findings'] = [
                f"Average Recall: {avg_recall:.1%} - catches about half of bad markets",
                f"Average Precision: {avg_precision:.1%} - reasonable false alarm rate",
                "Model useful as one input in multi-factor risk assessment",
                "Consider combining with other risk signals for better coverage"
            ]
            summary['recommendations'] = [
                "Use as supporting indicator, not sole trading signal",
                "Combine with other risk metrics (volatility, correlation breakdown)",
                "Focus on 48h horizon for best signal quality",
                "Requires human judgment for final risk decisions"
            ]
        else:
            summary['conclusion'] = "LIMITED PREDICTABILITY - Model shows weak signal, more refinement needed"
            summary['key_findings'] = [
                f"Average Recall: {avg_recall:.1%} - missing most bad markets",
                f"Average Precision: {avg_precision:.1%} - high false alarm rate",
                "Current feature set may not be sufficient",
                "Consider additional features or data sources"
            ]
            summary['recommendations'] = [
                "Investigate additional indicators (volatility, correlation, flow)",
                "Test different regime definitions (BTC threshold variations)",
                "Consider ensemble approach with multiple models",
                "Review feature engineering for potential improvements"
            ]

        logger.info(f"\n{summary['conclusion']}")
        logger.info(f"\nKey Findings:")
        for finding in summary['key_findings']:
            logger.info(f"  • {finding}")

        logger.info(f"\nRecommendations:")
        for rec in summary['recommendations']:
            logger.info(f"  • {rec}")

        return summary

    def save_report(self, summary: Dict):
        """Save report to JSON"""
        report_file = self.output_dir / 'regime_analysis_summary.json'

        with open(report_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"\n✓ Report saved to {report_file}")

    # ========================================================================
    # VISUALIZATION
    # ========================================================================

    def generate_visualizations(self, df: pd.DataFrame, accuracy_results: Dict):
        """Generate matplotlib visualizations"""
        if not PLOTTING_AVAILABLE:
            logger.warning("Plotting libraries not available - skipping visualizations")
            return

        logger.info("=" * 80)
        logger.info("GENERATING VISUALIZATIONS")
        logger.info("=" * 80)

        try:
            # Set style
            sns.set_style("darkgrid")

            # 1. Confusion matrices
            fig, axes = plt.subplots(1, 3, figsize=(15, 4))

            for idx, horizon in enumerate(['24h', '48h', '72h']):
                if horizon not in accuracy_results:
                    continue

                metrics = accuracy_results[horizon]
                cm = np.array([
                    [metrics['true_negatives'], metrics['false_positives']],
                    [metrics['false_negatives'], metrics['true_positives']]
                ])

                sns.heatmap(cm, annot=True, fmt='d', ax=axes[idx], cmap='Blues',
                           xticklabels=['NORMAL', 'BAD'],
                           yticklabels=['NORMAL', 'BAD'])
                axes[idx].set_title(f'Confusion Matrix ({horizon})')
                axes[idx].set_ylabel('Actual')
                axes[idx].set_xlabel('Predicted')

            plt.tight_layout()
            conf_matrix_file = self.output_dir / 'confusion_matrices.png'
            plt.savefig(conf_matrix_file, dpi=150, bbox_inches='tight')
            logger.info(f"✓ Saved confusion matrices to {conf_matrix_file}")
            plt.close()

            # 2. Metrics comparison
            fig, axes = plt.subplots(2, 2, figsize=(12, 8))

            horizons = list(accuracy_results.keys())
            metrics_names = ['accuracy', 'precision', 'recall', 'f1_score']

            for idx, metric_name in enumerate(metrics_names):
                ax = axes[idx // 2, idx % 2]
                values = [accuracy_results[h][metric_name] for h in horizons]

                ax.bar(horizons, values, color='steelblue', alpha=0.7)
                ax.set_ylim([0, 1])
                ax.set_ylabel('Score')
                ax.set_title(f'{metric_name.replace("_", " ").title()}')
                ax.grid(True, alpha=0.3)

                # Add value labels
                for i, v in enumerate(values):
                    ax.text(i, v + 0.02, f'{v:.2f}', ha='center', va='bottom')

            plt.tight_layout()
            metrics_file = self.output_dir / 'model_metrics.png'
            plt.savefig(metrics_file, dpi=150, bbox_inches='tight')
            logger.info(f"✓ Saved metrics comparison to {metrics_file}")
            plt.close()

        except Exception as e:
            logger.warning(f"Visualization generation failed: {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution"""
    logger.info("\n" + "=" * 80)
    logger.info("REGIME ANALYSIS & REPORTING")
    logger.info("=" * 80)

    try:
        reporter = RegimeAnalysisReport()

        # Load data
        df = reporter.load_predictions_and_actuals()

        if df.empty:
            logger.warning("No prediction data available for analysis")
            return False

        # Run analyses
        accuracy_results = reporter.analyze_prediction_accuracy(df)
        importance_results = reporter.analyze_feature_importance()
        transition_results = reporter.analyze_regime_transitions(df)

        # Generate summary
        summary = reporter.generate_summary_report(accuracy_results, importance_results, transition_results)

        # Save and visualize
        reporter.save_report(summary)
        reporter.generate_visualizations(df, accuracy_results)

        logger.info("\n" + "=" * 80)
        logger.info("✅ ANALYSIS COMPLETE")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
