#!/usr/bin/env python3
import os
import sys
import warnings
from dotenv import load_dotenv

# Load environment variables from .env BEFORE everything else
load_dotenv()

"""
magicpin AI Challenge — LLM-Powered Judge Simulator
====================================================

A strict but fair judge that scores your bot and explains WHY.
"""

# =============================================================================
# ██████  CONFIGURATION - EDIT THIS SECTION ██████
# =============================================================================

# Your bot's URL (Point to LOCAL for terminal testing)
BOT_URL = "http://localhost:8000"

# Choose your LLM provider
LLM_PROVIDER = "groq"

# Your API key (Automated from .env)
LLM_API_KEY = os.getenv("GROQ_API_KEY", "")

# Model to use
LLM_MODEL = "llama-3.1-8b-instant"

# Which test to run by default
TEST_SCENARIO = "warmup"

# =============================================================================
# ██████  END OF CONFIGURATION - DON'T EDIT BELOW THIS LINE ██████
# =============================================================================

import json
import time
import re
import socket
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from urllib import request as urlrequest, error as urlerror
from abc import ABC, abstractmethod

# Suppress all warnings (clean terminal)
warnings.filterwarnings("ignore")

# Constants
TIMEOUT_LLM = 45
DATASET_DIR = Path(__file__).parent / "dataset"

# =============================================================================
# TERMINAL OUTPUT
# =============================================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[35m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.RESET}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

def print_section(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.RESET}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}[PASS]{Colors.RESET} {text}")

def print_fail(text: str):
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {text}")

def print_info(text: str):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {text}")

def print_warn(text: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {text}")

# =============================================================================
# LLM PROVIDERS
# =============================================================================

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        pass
    
    @abstractmethod
    def name(self) -> str:
        pass

class GroqProvider(LLMProvider):
    def name(self): return f"Groq ({LLM_MODEL})"
    def complete(self, prompt: str):
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        req = urlrequest.Request(url, data=json.dumps(data).encode(), headers=headers)
        with urlrequest.urlopen(req, timeout=TIMEOUT_LLM) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]

# ... (rest of the script is identical, I will only show the top fix to keep it clean)
