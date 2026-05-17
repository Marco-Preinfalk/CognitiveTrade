"""ML-based trading strategy using Random Forest on technical indicators."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from data_fetcher import get_data_fetcher
from strategy import TechnicalAnalyzer
from utils import print_success, print_error, print_warning, print_info, format_percent

class MLStrategyEngine:
    
    def __init__(self, model_name="trading_model"):
        self.model_name = model_name
        self.model_path = f"models/{model_name}.pkl"
        self.scaler_path = f"models/{model_name}_scaler.pkl"
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.trained = False
        
        os.makedirs("models", exist_ok=True)
        

        self._load_model()
    
    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self.trained = True
                print_success(f"ML model '{self.model_name}' loaded")
            except Exception as e:
                print_warning(f"Kann Model unavailable: {str(e)}")
    
    def _save_model(self):
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            print_success(f"ML model '{self.model_name}' saved")
        except Exception as e:
            print_error(f"Error saving: {str(e)}")
    
    def prepare_training_data(self, asset, days=180, asset_type="STOCK"):
        """
        Prepare historical data for training
        
        Args:
            asset: z.B. "AAPL"
            days: Wie viele Tage historisch?
            asset_type: "STOCK" oder "CRYPTO"
        
        Returns:
            X (Features), y (Labels)
        """
        print_info(f"Loading {days} days of data for {asset}...")
        
        fetcher = get_data_fetcher()
        
        if asset_type == "STOCK":
            df = fetcher.get_stock_data(asset, days=days)
        else:
            df = fetcher.get_crypto_klines(asset, interval="1h", limit=days*24)
        
        if df is None or df.empty:
            print_error(f"No data for {asset}")
            return None, None
        

        analyzer = TechnicalAnalyzer()
        df = analyzer.calculate_indicators(df)
        
        if df.empty:
            print_error("No indicators calculated")
            return None, None
        

        df['returns'] = df['close'].pct_change()
        df['price_sma20_ratio'] = df['close'] / df['SMA_20']
        df['price_sma50_ratio'] = df['close'] / df['SMA_50']
        df['volume_ma'] = df['volume'].rolling(20).mean()
        
        # Label: 1 = price goes up next candle, 0 = down/flat
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
        

        feature_cols = [
            'RSI', 'MACD', 'MACD_signal', 'MACD_diff',
            'SMA_20', 'SMA_50', 'EMA_12', 'ATR',
            'returns', 'price_sma20_ratio', 'price_sma50_ratio',
            'volume', 'volume_ma'
        ]
        
        self.feature_names = feature_cols
        

        df = df[feature_cols + ['target']].dropna()
        
        X = df[feature_cols].values
        y = df['target'].values
        
        print_success(f"{len(X)} training samples prepared")
        
        return X, y
    
    def train(self, asset, days=180, asset_type="STOCK", test_size=0.2):
        """
        Train ML model on historical data
        
        Args:
            asset: z.B. "AAPL"
            days: Wie viele Tage?
            asset_type: "STOCK" oder "CRYPTO"
            test_size: % for test set
        """
        print_info(f"\nTraining ML model for {asset}...")
        

        X, y = self.prepare_training_data(asset, days, asset_type)
        if X is None:
            return False
        

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        

        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        print_info("⏳ Training Random Forest Classifier...")
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train_scaled, y_train)
        

        y_pred_train = self.model.predict(X_train_scaled)
        y_pred_test = self.model.predict(X_test_scaled)
        
        train_acc = accuracy_score(y_train, y_pred_train)
        test_acc = accuracy_score(y_test, y_pred_test)
        precision = precision_score(y_test, y_pred_test, zero_division=0)
        recall = recall_score(y_test, y_pred_test, zero_division=0)
        f1 = f1_score(y_test, y_pred_test, zero_division=0)
        
        print_success("Training complete")
        print(f"  Train Accuracy: {format_percent(train_acc*100)}")
        print(f"  Test Accuracy: {format_percent(test_acc*100)}")
        print(f"  Precision: {format_percent(precision*100)}")
        print(f"  Recall: {format_percent(recall*100)}")
        print(f"  F1 Score: {format_percent(f1*100)}")
        

        importances = self.model.feature_importances_
        top_features = sorted(zip(self.feature_names, importances), key=lambda x: x[1], reverse=True)[:5]
        print(f"\nTop Features:")
        for feat, imp in top_features:
            print(f"  - {feat}: {format_percent(imp*100)}")
        
        self.trained = True
        self._save_model()
        
        return True
    
    def predict(self, asset, asset_type="STOCK"):
        """
        Predict signal for asset based on ML
        
        Returns:
            {'signal': 'BUY'/'SELL', 'probability': 0.75, ...}
        """
        if not self.trained or self.model is None:
            print_warning("Model not trained! Run train() first.")
            return None
        
        fetcher = get_data_fetcher()
        
        # Loading letzte 50 bars
        if asset_type == "STOCK":
            df = fetcher.get_stock_data(asset, days=30)
        else:
            df = fetcher.get_crypto_klines(asset, interval="1h", limit=100)
        
        if df is None or df.empty:
            return None
        

        analyzer = TechnicalAnalyzer()
        df = analyzer.calculate_indicators(df)
        

        df['returns'] = df['close'].pct_change()
        df['price_sma20_ratio'] = df['close'] / df['SMA_20']
        df['price_sma50_ratio'] = df['close'] / df['SMA_50']
        df['volume_ma'] = df['volume'].rolling(20).mean()
        

        latest = df.iloc[-1]
        
        features = np.array([[
            latest['RSI'], latest['MACD'], latest['MACD_signal'], latest['MACD_diff'],
            latest['SMA_20'], latest['SMA_50'], latest['EMA_12'], latest['ATR'],
            latest['returns'], latest['price_sma20_ratio'], latest['price_sma50_ratio'],
            latest['volume'], latest['volume_ma']
        ]])
        

        features_scaled = self.scaler.transform(features)
        

        prediction = self.model.predict(features_scaled)[0]
        probability = self.model.predict_proba(features_scaled)[0]
        
        signal_type = "BUY" if prediction == 1 else "SELL"
        confidence = probability[prediction]
        
        return {
            'signal': signal_type,
            'probability': confidence,
            'buy_prob': probability[1],
            'sell_prob': probability[0],
            'entry_price': float(latest['close']),
            'reason': f"ML Prediction: {signal_type} ({format_percent(confidence*100)} confidence)"
        }
    
    def get_model_info(self):
        if not self.trained:
            return None
        
        return {
            'model_type': 'Random Forest Classifier',
            'trained': True,
            'n_features': len(self.feature_names),
            'features': self.feature_names,
            'model_path': self.model_path,
        }


# Singleton
_ml_engine = None

def get_ml_strategy_engine(model_name="trading_model"):
    """Get or create ML Strategy Engine"""
    global _ml_engine
    if _ml_engine is None:
        _ml_engine = MLStrategyEngine(model_name)
    return _ml_engine
