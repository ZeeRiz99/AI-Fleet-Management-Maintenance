"""Train the breakdown-risk model (XGBoost) with a TIME-based split and report metrics.

Split:  train  snapshots <  2024-12-01   (last 6 months of it = validation, used to pick threshold)
        gap    2024-12-01 .. 2024-12-31  (30-day label horizon would otherwise leak into test)
        test   snapshots >= 2025-01-01
Run:  python src/train.py
"""
import json

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import shap
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from xgboost import XGBClassifier

import config as C

LABEL = "breakdown_next_30d"
TRAIN_END, VAL_START, TEST_START = "2024-12-01", "2024-06-01", "2025-01-01"
MODEL_DIR = C.ROOT / "models"
REPORT_DIR = C.ROOT / "reports"


def load_xy():
    df = pd.read_csv(C.PROCESSED / "features.csv", parse_dates=["snapshot_date"])
    df = pd.get_dummies(df, columns=["vehicle_type"], dtype=int)
    feats = [c for c in df.columns if c not in ("vehicle_id", "snapshot_date", "depot_id", LABEL)]  # depot_id: spurious
    return df, feats


def report(name, y, score, thr):
    pred = score >= thr
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    top = np.argsort(-score)[: max(1, len(y) // 10)]  # top 10% riskiest snapshots
    return {"model": name, "roc_auc": round(roc_auc_score(y, score), 3),
            "pr_auc": round(average_precision_score(y, score), 3), "threshold": round(float(thr), 3),
            "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
            "precision_top10pct": round(float(y.iloc[top].mean()), 3)}


def best_f1_threshold(y, score):
    grid = np.unique(np.quantile(score, np.linspace(0.5, 0.99, 100)))
    return max(grid, key=lambda t: precision_recall_fscore_support(y, score >= t, average="binary", zero_division=0)[2])


def main():
    df, feats = load_xy()
    d = df.snapshot_date
    train, test = df[d < TRAIN_END], df[d >= TEST_START]
    fit, val = train[train.snapshot_date < VAL_START], train[train.snapshot_date >= VAL_START]
    print(f"fit {len(fit)} | val {len(val)} | test {len(test)} | test positive rate {test[LABEL].mean():.3f}")

    params = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                  min_child_weight=5, eval_metric="aucpr", random_state=C.SEED)
    # No scale_pos_weight: positives are ~16%, and unweighted probabilities stay calibrated, which the
    # cost-impact layer needs (expected loss = probability x cost). The threshold handles the imbalance.
    model = XGBClassifier(**params).fit(fit[feats], fit[LABEL])
    thr = best_f1_threshold(val[LABEL], model.predict_proba(val[feats])[:, 1])

    # refit on all training data, keep the validation-chosen threshold
    model = XGBClassifier(**params).fit(train[feats], train[LABEL])
    score = model.predict_proba(test[feats])[:, 1]

    # baseline: overdue-service rule only
    base_val = val.service_debt.fillna(0)
    base_thr = best_f1_threshold(val[LABEL], base_val)
    results = [report("XGBoost", test[LABEL], pd.Series(score, index=test.index), thr),
               report("Baseline: service_debt rule", test[LABEL], test.service_debt.fillna(0), base_thr),
               {"model": "Random (prevalence)", "pr_auc": round(test[LABEL].mean(), 3), "roc_auc": 0.5}]
    res = pd.DataFrame(results)
    print(res.to_string(index=False))
    print(f"calibration on test: mean predicted {score.mean():.3f} vs actual {test[LABEL].mean():.3f}")

    MODEL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": model, "features": feats, "threshold": float(thr)}, MODEL_DIR / "risk_model.joblib")
    res.to_csv(REPORT_DIR / "risk_model_metrics.csv", index=False)

    # explainability: mean |SHAP| on the test set
    sv = shap.TreeExplainer(model).shap_values(test[feats])
    imp = pd.Series(np.abs(sv).mean(0), index=feats).sort_values(ascending=False)
    imp.to_csv(REPORT_DIR / "shap_importance.csv", header=["mean_abs_shap"])
    px.bar(imp.head(15).iloc[::-1], orientation="h", title="Top drivers of breakdown risk (mean |SHAP|)"
           ).write_html(REPORT_DIR / "shap_importance.html")
    print("\nTop features (mean |SHAP|):\n" + imp.head(10).round(3).to_string())
    json.dump({"train_end": TRAIN_END, "test_start": TEST_START, "n_features": len(feats)},
              open(REPORT_DIR / "split.json", "w"))


if __name__ == "__main__":
    main()
