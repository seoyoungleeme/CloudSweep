# FinOps Report - L1-005

## Problem Identification

Two Application Load Balancers show no request or active connection activity during the 30-day metrics window.

| Resource | Severity | Evidence | Estimated Waste |
|----------|----------|----------|-----------------|
| lb-4dzo8v | HIGH | request_count = 0, active_connection_count = 0 | $16.43/mo |
| lb-ucc4pu | HIGH | request_count = 0, active_connection_count = 0 | $16.43/mo |

## Cost Evidence

ALB fixed cost: $0.0225/hr x 730hr x 2 = $32.85/mo. LCU cost is excluded because traffic is zero.

## Root Cause

The load balancers appear to be retained after their traffic paths were removed or moved elsewhere. They still accrue hourly fixed charges even without active traffic.

## Proposed Solution

Validate DNS and listener dependencies, then remove the two idle ALBs. After deletion, remove associated security groups if they are no longer referenced.

## Estimated Monthly Savings

$32.85/mo