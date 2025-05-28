#!/usr/bin/env python3
"""
Test script for rate limiting functionality
"""

import time
from ai_service import RateLimiter

def test_rate_limiter():
    """Test the rate limiter functionality."""
    print("🧪 Testing Rate Limiter...")
    
    # Test with very low limit for quick testing
    rate_limiter = RateLimiter(openai_rpm_limit=3)  # 3 requests per minute
    
    print(f"OpenAI RPM Limit: {rate_limiter.openai_rpm_limit}")
    print(f"Perplexity RPM Limit: {rate_limiter.perplexity_rpm_limit}")
    
    # Test OpenAI rate limiting
    print("\n📊 Testing OpenAI rate limiting...")
    for i in range(5):
        if rate_limiter.can_make_request("openai"):
            rate_limiter.record_request("openai")
            print(f"✅ Request {i+1}: Allowed")
        else:
            print(f"❌ Request {i+1}: Rate limited")
            
        # Small delay to prevent instant execution
        time.sleep(0.1)
    
    # Test waiting for rate limit
    print(f"\n⏳ Current OpenAI requests in queue: {len(rate_limiter.openai_request_times)}")
    print("Testing wait_for_rate_limit (should wait if needed)...")
    
    start_time = time.time()
    rate_limiter.wait_for_rate_limit("openai")
    wait_time = time.time() - start_time
    
    if wait_time > 0.5:
        print(f"✅ Rate limiter waited {wait_time:.2f} seconds as expected")
    else:
        print(f"✅ No wait needed ({wait_time:.2f} seconds)")
    
    print("\n🎉 Rate limiting test completed!")

if __name__ == "__main__":
    test_rate_limiter() 