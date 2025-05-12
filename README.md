# Condvest Trading Analytics - Real-Time Market Data Pipeline

## Overview
This project implements a robust real-time market data pipeline that serves as the backbone for Condvest Trading Analytics. The system fetches and processes 1-minute candlestick data for stocks in real-time, validates the data quality, and stores it in a TimescaleDB database for efficient time-series analysis.

## Features
- Real-time 1-minute candlestick data collection
- Automated data validation and quality checks
- Efficient storage in TimescaleDB for time-series analysis
- Daily candle aggregation and validation
- Docker containerization for easy deployment
- Robust error handling and logging

## Prerequisites
- Python 3.10+
- Docker
- TimescaleDB
- Required Python packages (see requirements.txt)

## Installation

1. Clone the repository:
