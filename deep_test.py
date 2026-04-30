"""
Deep Test Harness - Simulates the real magicpin judge evaluation.
Tests every trigger, every reply scenario, and flags issues.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import time
import requests
import sys

BASE = "http://localhost:8000"
BANNED_PHRASES = [
    "analyzed your business visibility",
    "noticed a growth opportunity", 
    "noticed a specific growth",
    "exciting news",
    "hi there",
    "hi partner",
    "trends in your area",
    "update your local highlights to maintain visibility",
]

def load_seeds():
    with open("dataset/categories/dentists.json") as f: cats = {"dentists": json.load(f)}
    for name in ["salons", "restaurants", "pharmacies", "gyms"]:
        try:
            with open(f"dataset/categories/{name}.json") as f: cats[name] = json.load(f)
        except: pass
    with open("dataset/merchants_seed.json") as f: merchants = {m["merchant_id"]: m for m in json.load(f)["merchants"]}
    with open("dataset/triggers_seed.json") as f: triggers = {t["id"]: t for t in json.load(f)["triggers"]}
    with open("dataset/customers_seed.json") as f: customers = {c["customer_id"]: c for c in json.load(f)["customers"]}
    return cats, merchants, triggers, customers

def push_contexts(cats, merchants, triggers, customers):
    print("\n=== PUSHING CONTEXTS ===")
    for slug, data in cats.items():
        r = requests.post(f"{BASE}/v1/context", json={"scope": "category", "context_id": slug, "version": 1, "payload": data, "delivered_at": "2026-04-30T00:00:00Z"})
        print(f"  Category {slug}: {r.status_code}")
    for mid, data in merchants.items():
        r = requests.post(f"{BASE}/v1/context", json={"scope": "merchant", "context_id": mid, "version": 1, "payload": data, "delivered_at": "2026-04-30T00:00:00Z"})
        print(f"  Merchant {mid[:30]}: {r.status_code}")
    for tid, data in triggers.items():
        r = requests.post(f"{BASE}/v1/context", json={"scope": "trigger", "context_id": tid, "version": 1, "payload": data, "delivered_at": "2026-04-30T00:00:00Z"})
        print(f"  Trigger {tid[:40]}: {r.status_code}")
    for cid, data in customers.items():
        r = requests.post(f"{BASE}/v1/context", json={"scope": "customer", "context_id": cid, "version": 1, "payload": data, "delivered_at": "2026-04-30T00:00:00Z"})
        print(f"  Customer {cid[:30]}: {r.status_code}")

def test_tick(trigger_ids):
    r = requests.post(f"{BASE}/v1/tick", json={"now": "2026-04-30T12:00:00Z", "available_triggers": trigger_ids}, timeout=120)
    return r.json()

def check_action(action, trigger_id, trigger_data, merchant_data):
    """Check a single action for quality issues."""
    issues = []
    body = action.get("body", "")
    body_lower = body.lower()
    
    # Check banned phrases
    for phrase in BANNED_PHRASES:
        if phrase in body_lower:
            issues.append(f"BANNED PHRASE: '{phrase}'")
    
    # Check if body is empty or too short
    if len(body) < 20:
        issues.append(f"BODY TOO SHORT: {len(body)} chars")
    
    # Check merchant name usage
    owner = merchant_data.get("identity", {}).get("owner_first_name", "")
    merchant_name = merchant_data.get("identity", {}).get("name", "")
    if owner and owner.lower() not in body_lower and merchant_name.lower() not in body_lower:
        issues.append(f"MISSING MERCHANT NAME: Expected '{owner}' or '{merchant_name}'")
    
    # Check trigger-specific data grounding
    payload = trigger_data.get("payload", {})
    kind = trigger_data.get("kind", "")
    
    if kind == "regulation_change":
        if "dci" not in body_lower and "dental council" not in body_lower:
            issues.append("COMPLIANCE: Missing authority (DCI/Dental Council)")
        if "radiograph" not in body_lower and "x-ray" not in body_lower and "film" not in body_lower:
            issues.append("COMPLIANCE: Missing specific rule (radiograph/X-ray)")
        deadline = payload.get("deadline_iso", "")
        if deadline and deadline[:4] not in body:
            issues.append(f"COMPLIANCE: Missing deadline reference ({deadline})")
    
    elif kind == "recall_due":
        if "cleaning" not in body_lower and "recall" not in body_lower:
            issues.append("RECALL: Missing service reference")
        if "299" not in body and "₹" not in body:
            issues.append("RECALL: Missing pricing")
    
    elif kind == "perf_dip":
        delta = payload.get("delta_pct", 0)
        if str(abs(int(delta * 100))) not in body:
            issues.append(f"PERF_DIP: Missing delta percentage ({abs(int(delta*100))}%)")
    
    elif kind == "supply_alert":
        molecule = payload.get("molecule", "")
        if molecule and molecule.lower() not in body_lower:
            issues.append(f"SUPPLY: Missing molecule name ({molecule})")
    
    elif kind == "ipl_match_today":
        match = payload.get("match", "")
        if match and match.lower().replace(" ", "") not in body_lower.replace(" ", ""):
            issues.append(f"IPL: Missing match reference ({match})")
    
    elif kind == "competitor_opened":
        comp = payload.get("competitor_name", "")
        if comp and comp.lower() not in body_lower:
            issues.append(f"COMPETITOR: Missing competitor name ({comp})")
    
    elif kind == "chronic_refill_due":
        mols = payload.get("molecule_list", [])
        found = sum(1 for m in mols if m.lower() in body_lower)
        if found == 0:
            issues.append(f"REFILL: Missing molecule names ({mols})")
    
    elif kind == "review_theme_emerged":
        theme = payload.get("theme", "")
        if theme and theme.replace("_", " ") not in body_lower and theme not in body_lower:
            issues.append(f"REVIEW: Missing theme reference ({theme})")
    
    # Check CTA (must end with a question)
    if "?" not in body:
        issues.append("ENGAGEMENT: No question mark in body (missing CTA)")
    
    # Check for template leakage
    if "{{" in body or "}}" in body or "[date]" in body_lower:
        issues.append("TEMPLATE LEAK: Unresolved template tags in body")
    
    return issues

def test_reply(conversation_id, message, expected_action):
    """Test the /v1/reply endpoint."""
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conversation_id,
        "message": message,
        "turn_number": 2,
        "from_role": "merchant",
        "received_at": "2026-04-30T12:00:00Z"
    }, timeout=30)
    data = r.json()
    actual = data.get("action", "unknown")
    body = data.get("body", "(no body)")
    
    return {
        "message": message[:60],
        "expected": expected_action,
        "actual": actual,
        "body": body,
        "passed": actual == expected_action
    }

def main():
    print("=" * 70)
    print("  DEEP TEST HARNESS — magicpin Judge Simulation")
    print("=" * 70)
    
    # Load data
    cats, merchants, triggers, customers = load_seeds()
    print(f"Loaded: {len(cats)} categories, {len(merchants)} merchants, {len(triggers)} triggers, {len(customers)} customers")
    
    # Push all contexts
    push_contexts(cats, merchants, triggers, customers)
    
    # Test ALL 25 triggers one at a time
    print("\n" + "=" * 70)
    print("  TRIGGER COMPOSITION TESTS")
    print("=" * 70)
    
    total_issues = 0
    trigger_results = []
    
    for tid, tdata in triggers.items():
        mid = tdata.get("merchant_id", "")
        mdata = merchants.get(mid, {})
        
        print(f"\n--- {tid} ---")
        try:
            result = test_tick([tid])
            actions = result.get("actions", [])
            
            if not actions:
                print(f"  ❌ NO ACTIONS RETURNED")
                total_issues += 1
                trigger_results.append({"id": tid, "issues": ["NO ACTIONS"], "body": ""})
                continue
            
            action = actions[0]
            body = action.get("body", "")
            print(f"  Body: \"{body[:80]}...\"")
            
            issues = check_action(action, tid, tdata, mdata)
            if issues:
                for iss in issues:
                    print(f"  ⚠️  {iss}")
                total_issues += len(issues)
            else:
                print(f"  ✅ PASSED")
            
            trigger_results.append({"id": tid, "issues": issues, "body": body[:80]})
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            total_issues += 1
            trigger_results.append({"id": tid, "issues": [str(e)], "body": ""})
    
    # Test /v1/reply scenarios
    print("\n" + "=" * 70)
    print("  REPLY HANDLING TESTS")
    print("=" * 70)
    
    reply_tests = [
        # Merchant engaged replies (should be action='send')
        ("conv_compliance_test", "Got it doc — need help auditing my X-ray setup. We have an old D-speed film unit.", "send"),
        ("conv_booking_test", "Yes please book me for Wed 5 Nov, 6pm.", "send"),
        ("conv_help_test", "Yes please, send me the checklist", "send"),
        ("conv_draft_test", "Sure, draft the update for me", "send"),
        ("conv_interested_test", "Sounds good, let's do it", "send"),
        ("conv_slot_test", "Reply 1", "send"),
        ("conv_schedule_test", "I'd like to schedule for Thursday 5pm", "send"),
        ("conv_audit_test", "Can you help with the compliance audit?", "send"),
        # Negative / ambiguous (should be action='wait')
        ("conv_stop_test", "Please stop sending me messages", "wait"),
        ("conv_unsub_test", "Unsubscribe me from this", "wait"),
    ]
    
    reply_passed = 0
    reply_failed = 0
    
    for conv_id, message, expected in reply_tests:
        result = test_reply(conv_id, message, expected)
        status = "✅" if result["passed"] else "❌"
        print(f"  {status} \"{result['message']}...\"")
        print(f"     Expected: {expected} | Got: {result['actual']} | Body: {result['body'][:50] if result['body'] else '(none)'}")
        if result["passed"]:
            reply_passed += 1
        else:
            reply_failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    
    passed_triggers = sum(1 for r in trigger_results if not r["issues"])
    failed_triggers = sum(1 for r in trigger_results if r["issues"])
    
    print(f"\n  Trigger Composition: {passed_triggers}/{len(trigger_results)} passed, {failed_triggers} with issues")
    print(f"  Reply Handling: {reply_passed}/{len(reply_tests)} passed, {reply_failed} failed")
    print(f"  Total Issues Found: {total_issues}")
    
    if failed_triggers > 0:
        print("\n  ⚠️  TRIGGERS WITH ISSUES:")
        for r in trigger_results:
            if r["issues"]:
                print(f"    - {r['id']}: {', '.join(r['issues'][:2])}")
    
    if reply_failed > 0:
        print("\n  ⚠️  FAILED REPLY TESTS:")
        for conv_id, message, expected in reply_tests:
            result = test_reply(conv_id, message, expected)
            if not result["passed"]:
                print(f"    - \"{message[:50]}\" expected={expected} got={result['actual']}")
    
    overall = passed_triggers + reply_passed
    total = len(trigger_results) + len(reply_tests)
    pct = int(overall / total * 100) if total > 0 else 0
    print(f"\n  OVERALL: {overall}/{total} ({pct}%)")
    
    if pct >= 90:
        print("  🏆 EXCELLENT — Ready for submission!")
    elif pct >= 70:
        print("  ✅ GOOD — Minor fixes needed")
    elif pct >= 50:
        print("  ⚠️  NEEDS WORK — Several issues to fix")
    else:
        print("  ❌ CRITICAL — Major issues found")

if __name__ == "__main__":
    main()
