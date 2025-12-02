
import datetime
from datetime import timezone

def calculate_decay(created_at, ref_time):
    # Ensure created_at is timezone aware
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)

    # Calculate time difference in hours
    time_diff = abs((created_at - ref_time).total_seconds()) / 3600.0
    
    # Apply gentle decay formula (12-hour half-life)
    decay_weight = 1.0 / (1.0 + (time_diff / 12.0))
    
    return time_diff, decay_weight

def test_historical_merge():
    print("Testing Historical Data Merge Logic...")
    
    # Scenario: Processing a post from Nov 26
    post_time = datetime.datetime(2025, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    
    # Case 1: Cluster is also from Nov 26 (should merge)
    cluster_time_1 = datetime.datetime(2025, 11, 26, 11, 50, 0, tzinfo=timezone.utc) # 10 mins older
    diff_1, score_1 = calculate_decay(post_time, cluster_time_1)
    print(f"Case 1 (Same Era): Diff={diff_1:.2f}h, Score={score_1:.4f} (Expected: > 0.9)")
    
    # Case 2: Cluster is from Nov 25 (24 hours older) - should have lower score but maybe mergeable if similarity is high
    cluster_time_2 = datetime.datetime(2025, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
    diff_2, score_2 = calculate_decay(post_time, cluster_time_2)
    print(f"Case 2 (24h Older): Diff={diff_2:.2f}h, Score={score_2:.4f} (Expected: ~0.33)")
    
    # Case 3: Cluster is from Nov 30 (Future/System Time) - simulating the bug if we used NOW()
    # If we used NOW() (Nov 30) against Nov 26 post, diff would be 96 hours.
    # But here we are testing the FIX: comparing post_time to cluster_time.
    
    # Let's simulate the old bug to show the improvement
    system_time_now = datetime.datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)
    bug_diff = abs((system_time_now - cluster_time_1).total_seconds()) / 3600.0
    bug_score = 1.0 / (1.0 + (bug_diff / 12.0))
    print(f"Old Bug Scenario (vs NOW): Diff={bug_diff:.2f}h, Score={bug_score:.4f} (Expected: Low, ~0.11)")

    if score_1 > 0.9 and score_2 > 0.3:
        print("\nSUCCESS: Logic correctly prioritizes relative time over wall-clock time.")
    else:
        print("\nFAILURE: Scores are not as expected.")

if __name__ == "__main__":
    test_historical_merge()
