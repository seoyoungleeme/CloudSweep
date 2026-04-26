# FinOps Report - L1-007

## Problem Identification

The scenario includes orphaned EBS snapshot storage that continues to generate monthly storage charges.

## Cost Evidence

EBS snapshots: 2TB x $0.05/GB = $100/mo.

## Root Cause

Snapshots were retained after their source volumes were no longer needed. Without lifecycle cleanup, old snapshots continue to accumulate cost.

## Proposed Solution

Verify recovery requirements, delete orphaned snapshots that are no longer needed, and add lifecycle automation for future snapshot cleanup.

## Estimated Monthly Savings

$100/mo