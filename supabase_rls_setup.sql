-- Supabase Row Level Security (RLS) Setup for MicroChips Database

-- 1. Enable RLS on all sensitive tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- 2. Create policies for the `users` table
-- Customers and Businesses can read and update their own user record
CREATE POLICY "Users can view their own profile" 
ON users FOR SELECT 
USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile" 
ON users FOR UPDATE 
USING (auth.uid() = id);

-- 3. Create policies for `business_profiles`
-- Business users can view and update their own business profile
CREATE POLICY "Businesses can view their own business profile" 
ON business_profiles FOR SELECT 
USING (auth.uid() = id);

CREATE POLICY "Businesses can update their own business profile" 
ON business_profiles FOR UPDATE 
USING (auth.uid() = id);

-- 4. Create policies for `orders`
-- Users can only view and create their own orders
CREATE POLICY "Users can view their own orders" 
ON orders FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own orders" 
ON orders FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- 5. Admin role-based access (Bypass RLS for Admins)
-- Assuming admin has `is_admin = true` in the users table, or using a specific role.
-- For simplicity, we can create a function to check if the current user is an admin.
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users WHERE id = auth.uid() AND is_admin = true
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add admin bypass policies
CREATE POLICY "Admins have full access to users" 
ON users FOR ALL 
USING (public.is_admin());

CREATE POLICY "Admins have full access to business profiles" 
ON business_profiles FOR ALL 
USING (public.is_admin());

CREATE POLICY "Admins have full access to orders" 
ON orders FOR ALL 
USING (public.is_admin());

-- Note: The python backend connecting via `DATABASE_URL` with the postgres connection string 
-- uses the `postgres` role, which naturally bypasses RLS by default.
-- These RLS policies will primarily secure the database if you query it directly from the frontend
-- using Supabase anon key, or if you switch the backend to respect RLS via postgREST.
